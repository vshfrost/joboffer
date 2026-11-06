"""Кроки для features/triage_*.feature і features/analysis_*.feature: use cases тріажу, аналізу,
вакансій і профілю + in-memory адаптери через портал.

Усі значення в кроках — у лапках і можуть бути порожніми, тому кроки — регулярні вирази з
іменованими групами. «Припустимо я проаналізував …» і «Якщо я аналізую …» — один і той самий
крок; у «Припустимо» додатково перевіряється, що дія вдалася. Вакансія — за номером на
користувача (`job_id`); внутрішній UUID у сценаріях не фігурує. Чернетка аналізу — поля, які
наступний крок «я аналізую» візьме до розбору (і забуде).
"""

import functools
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.analysis.use_cases import AnalysisUseCases
from application.contracts.actor import Actor, Channel, Scope
from application.contracts.analysis import (
    AnalysisBriefData,
    AnalysisData,
    AnalysisInput,
    GapInput,
)
from application.contracts.jobs import (
    JobData,
    JobInput,
    JobSearchInput,
    JobSummaryData,
)
from application.contracts.profile import (
    ContactsData,
    LocationsData,
    RulesData,
    SectionData,
    TargetData,
)
from application.contracts.triage import SavedTriageData, TriageBriefData, TriageInput
from application.jobs.use_cases import JobUseCases
from application.ports.prompts import PromptKey
from application.profile.use_cases import ProfileUseCases
from application.triage.use_cases import TriageUseCases
from domain.facts.fact import NewFact
from domain.facts.ids import FactId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.jobs.linkedin import linkedin_job_url
from domain.profile.profile import Profile
from domain.shared.errors import DomainError, InvalidFields, InvalidValue
from domain.triage.triage import Triage, TriageSource, TriageVerdict
from tests.support.analysis import InMemoryAnalysisUnitOfWork
from tests.support.clock import FakeClock
from tests.support.facts import InMemoryFactUnitOfWork
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store
from tests.support.profile import InMemoryProfileUnitOfWork
from tests.support.triage import InMemoryTriageUnitOfWork

scenarios(
    "features/triage_brief.feature",
    "features/triage_save.feature",
    "features/triage_list.feature",
    "features/triage_users.feature",
    "features/analysis_brief.feature",
    "features/analysis_save.feature",
    "features/analysis_stale.feature",
    "features/analysis_list.feature",
    "features/analysis_users.feature",
)

Step = Callable[..., Any]

TRIAGE_RULES = "Quick triage rules. Then call save_triage."
RUBRIC_TEMPLATE = (
    "Score for {candidate}. Domain fit with target domains{domain_examples}; "
    "gaps: what {candidate} lacks."
)
ITEM = re.compile(r"^\s*(\d+)=(-?\d+)/(.*?)/(.*)$")


class FakePrompts:
    """Шаблон рубрики з іменованими плейсхолдерами й правила тріажу — як у каталозі промптів."""

    def get(self, key: PromptKey) -> str:
        return {
            PromptKey.ANALYSIS_RUBRIC: RUBRIC_TEMPLATE,
            PromptKey.TRIAGE_RULES: TRIAGE_RULES,
        }[key]


def rx(pattern: str) -> Any:
    return parsers.re(pattern)


def succeeded(step: Step) -> Step:
    """Крок-передумова: дія має вдатися, інакше сценарій не про те."""

    @functools.wraps(step)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        step(*args, **kwargs)
        world: World = kwargs["world"]
        assert world.error is None, world.error

    return wrapper


def setup(pattern: Any) -> Callable[[Step], Step]:
    """Передумова, що читається і після «Припустимо», і після «Якщо» (через «І»)."""

    def decorate(step: Step) -> Step:
        parsed = rx(pattern) if isinstance(pattern, str) else pattern
        bdd_given(parsed, stacklevel=2)(step)
        bdd_when(parsed, stacklevel=2)(step)
        return step

    return decorate


def action(pattern: str) -> Callable[[Step], Step]:
    """Один текст — і «Припустимо я зробив …», і «Якщо я роблю …»."""

    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(succeeded(step))
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


def words(text: str) -> list[str]:
    """Елементи через «;»: порожній рядок — порожній список; пробіли навколо не мають значення."""
    return [] if text.strip() == "" else [part.strip() for part in text.split(";")]


def raw_items(text: str) -> list[str]:
    """Те саме, але як є — з пробілами й порожніми: чистить їх сервер, а не крок."""
    return [] if text == "" else text.split(";")


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.jobs_store = Store.empty()
        self.facts_store = FactStore.empty()
        self.profiles: dict[UserId, Profile] = {}
        self.saved_at: dict[UserId, datetime] = {}
        self.inputs_changed: dict[UserId, datetime] = {}
        prompts = FakePrompts()
        self.jobs = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.jobs_store), clock, ids
        )
        self.triage = TriageUseCases(
            lambda: InMemoryTriageUnitOfWork(
                self.jobs_store, self.profiles, self.inputs_changed, self.facts_store
            ),
            clock,
            ids,
            prompts,
        )
        self.analysis = AnalysisUseCases(
            lambda: InMemoryAnalysisUnitOfWork(
                self.jobs_store, self.facts_store, self.profiles, self.inputs_changed
            ),
            clock,
            ids,
            prompts,
        )
        self.profile = ProfileUseCases(
            lambda: InMemoryProfileUnitOfWork(
                self.profiles, self.saved_at, self.inputs_changed
            ),
            clock,
        )
        self.actors: dict[str, Actor] = {}
        self.current = ""
        self.sections: dict[str, dict[str, dict[str, Any]]] = {}
        self.draft: dict[str, str] = {}
        self.draft_gaps: list[GapInput] = []
        self.last_job = 0
        self.error: DomainError | None = None
        self.triage_brief: TriageBriefData | None = None
        self.saved_triage: SavedTriageData | None = None
        self.analysis_brief: AnalysisBriefData | None = None
        self.last_list: list[JobSummaryData] | None = None

    # --- користувачі й результат останньої дії ---------------------------------------------

    def become(self, name: str) -> None:
        if name not in self.actors:
            self.actors[name] = Actor(
                user_id=UserId(self.ids.new()),
                channel=Channel.WEB,
                client_id="web",
                grant_id=None,
                scopes=frozenset(Scope),
                correlation_id="test",
            )
            self.sections[name] = {}
        self.current = name
        self.reset_outcome()

    @property
    def actor(self) -> Actor:
        return self.actors[self.current]

    def reset_outcome(self) -> None:
        self.error = None
        self.triage_brief = None
        self.saved_triage = None
        self.analysis_brief = None
        self.last_list = None

    def attempt(self, call: Callable[[], Any]) -> Any:
        """Виконує дію; помилка домену запамʼятовується для кроків «Тоді»."""
        self.reset_outcome()
        try:
            return self.portal.call(call)
        except DomainError as error:
            self.error = error
            return None

    # --- вакансії ------------------------------------------------------------------------------

    def add_job(self, title: str, company: str, text: str) -> None:
        data = JobInput(text=text, title=title, company=company)
        self.attempt(lambda: self.jobs.add_job(self.actor, data))

    def seed_alert(self, title: str) -> None:
        """Вакансія з листа-алерту LinkedIn без тексту: її створить B10, тут — передумова."""
        number = len(self.job_titles()) + 1
        linkedin_id = str(4_012_345_000 + number)

        async def seed() -> None:
            async with InMemoryJobUnitOfWork(self.jobs_store) as uow:
                await uow.jobs.add(
                    self.actor.user_id,
                    JobId(self.ids.new()),
                    NewJob(
                        text=None,
                        url=linkedin_job_url(linkedin_id),
                        title=title,
                        linkedin_id=linkedin_id,
                        source="linkedin_alert",
                    ),
                    self.clock.now(),
                )
                await uow.commit()

        self.portal.call(seed)

    def job_titles(self) -> list[str]:
        everything = self.portal.call(
            self.jobs.list_jobs,
            self.actor,
            JobSearchInput(limit=200),
        )
        hidden = self.portal.call(
            self.jobs.list_jobs,
            self.actor,
            JobSearchInput(dismissed=True, limit=200),
        )
        return [item.title or "" for item in [*everything, *hidden]]

    def job(self, number: int) -> JobData:
        return self.portal.call(self.jobs.get_job, self.actor, number)

    def search(self, **fields: Any) -> None:
        data = JobSearchInput(**fields)
        self.last_list = self.attempt(lambda: self.jobs.list_jobs(self.actor, data))

    def current_list(self) -> list[JobSummaryData]:
        assert self.error is None, self.error
        assert self.last_list is not None, "список не переглядали"
        return self.last_list

    def row(self, title: str) -> JobSummaryData:
        found = [item for item in self.current_list() if (item.title or "") == title]
        assert len(found) == 1, (title, found)
        return found[0]

    # --- факти ---------------------------------------------------------------------------------

    def add_fact(self, kind: str, text: str, confirmed: bool) -> None:
        async def add() -> None:
            async with InMemoryFactUnitOfWork(self.facts_store) as uow:
                added = await uow.facts.add(
                    self.actor.user_id,
                    FactId(self.ids.new()),
                    NewFact.parse(kind=kind, text=text),
                    self.clock.now(),
                )
                if confirmed:
                    await uow.facts.confirm(
                        self.actor.user_id, [added.number], self.clock.now()
                    )
                await uow.commit()

        self.portal.call(add)

    # --- профіль -------------------------------------------------------------------------------

    def save_section(self, section: str, **fields: Any) -> None:
        """Зберігає розділ через use case, як веб чи MCP: розділ = попередні поля + нові."""
        state = self.sections[self.current].setdefault(section, {})
        state.update(fields)
        data: SectionData
        if section == "target":
            data = TargetData(
                roles=tuple(state.get("roles", ())),
                seniority=tuple(state.get("seniority", ())),
                min_salary_eur=state.get("min_salary_eur"),
                target_domains=tuple(state.get("target_domains", ())),
            )
        elif section == "locations":
            data = LocationsData(work_modes=tuple(state.get("work_modes", ())))
        elif section == "rules":
            data = RulesData(stop_words=tuple(state.get("stop_words", ())))
        else:
            data = ContactsData(
                full_name=state.get("full_name", ""), email=state.get("email", "")
            )
        self.attempt(lambda: self.profile.save_section(self.actor, data))

    # --- тріаж ---------------------------------------------------------------------------------

    def save_triage(self, items: list[TriageInput]) -> None:
        self.saved_triage = self.attempt(
            lambda: self.triage.save_triage(self.actor, items)
        )

    def triage_of(self, number: int) -> Any:
        return self.job(number).triage

    # --- аналіз --------------------------------------------------------------------------------

    def analyse(self, number: int, score: int) -> None:
        draft, self.draft = self.draft, {}
        draft_gaps, self.draft_gaps = self.draft_gaps, []

        def number_or_none(name: str) -> int | None:
            return int(draft[name]) if draft.get(name, "").strip() else None

        relocation = {"так": True, "ні": False}.get(draft.get("relocation", ""))
        data = AnalysisInput(
            score=score,
            summary=draft.get("summary", "Підсумок."),
            must_have=raw_items(draft.get("must_have", "")),
            nice_to_have=raw_items(draft.get("nice_to_have", "")),
            keywords=raw_items(draft.get("keywords", "")),
            seniority=draft.get("seniority", ""),
            work_mode=draft.get("work_mode", ""),
            location=draft.get("location", ""),
            languages=raw_items(draft.get("languages", "")),
            salary_min_eur=number_or_none("salary_min_eur"),
            salary_max_eur=number_or_none("salary_max_eur"),
            relocation=relocation,
            reasons=raw_items(draft.get("reasons", "")),
            gaps=[*raw_items(draft.get("gaps", "")), *draft_gaps],
        )
        self.last_job = number
        self.attempt(lambda: self.analysis.save_analysis(self.actor, number, data))

    def analysis_of(self, number: int) -> AnalysisData:
        return self.portal.call(self.analysis.get_analysis, self.actor, number)

    def field(self, number: int, name: str) -> str:
        analysis = self.analysis_of(number)
        value: Any = getattr(analysis, name)
        if value is None:
            return ""
        if isinstance(value, bool):
            return "так" if value else "ні"
        if name == "gaps":
            return "; ".join(item.gap for item in value)
        if isinstance(value, tuple):
            return "; ".join(value)
        return str(getattr(value, "value", value))


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


# --- хто я, час, передумови ------------------------------------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@bdd_given(rx(r"^минає (?P<hours>\d+) год (?P<minutes>\d+) хв$"))
@bdd_when(rx(r"^минає (?P<hours>\d+) год (?P<minutes>\d+) хв$"))
def time_passes(world: World, hours: str, minutes: str) -> None:
    world.clock.advance(timedelta(hours=int(hours), minutes=int(minutes)))


@bdd_given(rx(r"^минає (?P<days>\d+) (?:доба|доби|діб)$"))
@bdd_when(rx(r"^минає (?P<days>\d+) (?:доба|доби|діб)$"))
def days_pass(world: World, days: str) -> None:
    world.clock.advance(timedelta(days=int(days)))


@setup(
    rx(
        r'^є вакансія "(?P<title>[^"]*)" компанії "(?P<company>[^"]*)" з текстом "(?P<text>[^"]*)"$'
    )
)
def job_with_company(world: World, title: str, company: str, text: str) -> None:
    world.add_job(title, company, text)
    assert world.error is None, world.error


@setup(r'^є вакансія "(?P<title>[^"]*)" з текстом "(?P<text>[^"]*)"$')
def job_with_text(world: World, title: str, text: str) -> None:
    # «|» у тексті — перенос рядка (у рядку сценарію його не запишеш).
    world.add_job(title, "", text.replace("|", "\n"))
    assert world.error is None, world.error


@setup(rx(r'^крон оцінив вакансію (?P<number>\d+) як "(?P<verdict>[a-z]+)"$'))
def rated_by_rules(world: World, number: str, verdict: str) -> None:
    key = (world.actor.user_id, int(number))
    world.jobs_store.triage[key] = Triage(
        int(number),
        50,
        TriageVerdict(verdict),
        "Rules",
        world.clock.now(),
        TriageSource.RULES,
    )
    world.jobs_store.rules_hashes[key] = "hash"


@setup(r'^є вакансія "(?P<title>[^"]*)" з текстом із (?P<length>\d+) символів$')
def job_with_long_text(world: World, title: str, length: str) -> None:
    world.add_job(title, "", "x" * int(length))
    assert world.error is None, world.error


@setup(r'^є вакансія "(?P<title>[^"]*)" з листа-алерту без тексту$')
def alert_job(world: World, title: str) -> None:
    world.seed_alert(title)


@setup(r"^є ще (?P<count>\d+) вакансі\w+$")
def more_jobs(world: World, count: str) -> None:
    for number in range(int(count)):
        world.add_job(f"Додаткова {number}", "", f"Додаткова вакансія {number}")
        assert world.error is None, world.error


@action(
    r"^я (?:сховав|ховаю) вакансію (?P<number>\d+) з причиною \"(?P<reason>[^\"]*)\"$"
)
def dismiss(world: World, number: str, reason: str) -> None:
    world.attempt(lambda: world.jobs.dismiss_jobs(world.actor, [int(number)], reason))


@setup(
    rx(
        r'^у мене є (?P<state>підтверджений|непідтверджений) факт (?P<kind>\w+) "(?P<text>[^"]*)"$'
    )
)
def fact(world: World, state: str, kind: str, text: str) -> None:
    world.add_fact(kind, text, confirmed=state == "підтверджений")


# --- профіль --------------------------------------------------------------------------------


@action(r'^я (?:задаю|задав) ролі "(?P<value>[^"]*)"$')
def set_roles(world: World, value: str) -> None:
    world.save_section("target", roles=words(value))


@action(r'^я (?:задаю|задав) цільові домени "(?P<value>[^"]*)"$')
def set_domains(world: World, value: str) -> None:
    world.save_section("target", target_domains=words(value))


@action(r'^я (?:задаю|задав) рівні "(?P<value>[^"]*)"$')
def set_seniority(world: World, value: str) -> None:
    world.save_section("target", seniority=words(value))


@action(r"^я (?:задаю|задав) мінімальну зарплату (?P<value>\d+)$")
def set_salary(world: World, value: str) -> None:
    world.save_section("target", min_salary_eur=int(value))


@action(r'^я (?:задаю|задав) формати "(?P<value>[^"]*)"$')
def set_modes(world: World, value: str) -> None:
    world.save_section("locations", work_modes=words(value))


@action(r'^я (?:задаю|задав) стоп-слова "(?P<value>[^"]*)"$')
def set_stop_words(world: World, value: str) -> None:
    world.save_section("rules", stop_words=words(value))


@action(r'^я (?:задаю|задав) ім\'я "(?P<value>[^"]*)"$')
def set_name(world: World, value: str) -> None:
    world.save_section("contacts", full_name=value)


@action(r'^я (?:задаю|задав) пошту "(?P<value>[^"]*)"$')
def set_email(world: World, value: str) -> None:
    world.save_section("contacts", email=value)


@action(r"^я (?:зберігаю|зберіг) ціль без змін$")
def resave_target(world: World) -> None:
    world.save_section("target")


# --- бриф тріажу --------------------------------------------------------------------------------


@bdd_when(rx(r"^я готую бриф тріажу$"))
def prepare_triage(world: World) -> None:
    world.triage_brief = world.attempt(lambda: world.triage.prepare_triage(world.actor))


@bdd_when(rx(r"^я готую бриф тріажу без контексту$"))
def prepare_triage_without_context(world: World) -> None:
    world.triage_brief = world.attempt(
        lambda: world.triage.prepare_triage(world.actor, include_context=False)
    )


@bdd_when(rx(r"^я готую бриф тріажу з лімітом (?P<limit>-?\d+)$"))
def prepare_triage_limited(world: World, limit: str) -> None:
    world.triage_brief = world.attempt(
        lambda: world.triage.prepare_triage(world.actor, int(limit))
    )


def brief_of(world: World) -> TriageBriefData:
    assert world.error is None, world.error
    assert world.triage_brief is not None, "бриф не готували"
    return world.triage_brief


@bdd_then("бриф тріажу порожній")
def brief_empty(world: World) -> None:
    assert brief_of(world).jobs == ()


@bdd_then(rx(r"^у брифі тріажу очікують (?P<count>\d+) вакансі\w+$"))
def brief_pending(world: World, count: str) -> None:
    assert brief_of(world).pending == int(count)


@bdd_then(rx(r"^у брифі тріажу (?P<count>\d+) вакансі\w+$"))
def brief_count(world: World, count: str) -> None:
    assert len(brief_of(world).jobs) == int(count)


@bdd_then(rx(r'^вакансії в брифі тріажу за порядком: "(?P<titles>[^"]*)"$'))
def brief_titles(world: World, titles: str) -> None:
    assert [job.title or "" for job in brief_of(world).jobs] == words(titles)


def candidate(world: World, title: str) -> Any:
    found = [job for job in brief_of(world).jobs if (job.title or "") == title]
    assert len(found) == 1, (title, found)
    return found[0]


@bdd_then(
    rx(
        r'^вакансія "(?P<title>[^"]*)" у брифі тріажу: компанія "(?P<company>[^"]*)", '
        r'джерело "(?P<source>[^"]*)", текст "(?P<text>[^"]*)"$'
    )
)
def brief_candidate(
    world: World, title: str, company: str, source: str, text: str
) -> None:
    job = candidate(world, title)
    assert (job.company or "", job.source, job.text) == (
        company,
        source,
        text.replace("|", "\n"),
    )


@bdd_then(
    rx(
        r'^текст вакансії "(?P<title>[^"]*)" у брифі тріажу має (?P<length>\d+) символів '
        r'і охоплює "(?P<scope>[^"]*)"$'
    )
)
def brief_text_length(world: World, title: str, length: str, scope: str) -> None:
    job = candidate(world, title)
    assert (len(job.text), job.text_scope.value) == (int(length), scope)


@bdd_then(
    rx(r'^текст вакансії "(?P<title>[^"]*)" у брифі тріажу охоплює "(?P<scope>[^"]*)"$')
)
def brief_text_scope(world: World, title: str, scope: str) -> None:
    assert candidate(world, title).text_scope.value == scope


@bdd_then(rx(r'^факти в брифі тріажу: "(?P<facts>[^"]*)"$'))
def brief_facts(world: World, facts: str) -> None:
    brief = brief_of(world)
    assert brief.facts is not None
    assert [f"{fact.kind}={fact.text}" for fact in brief.facts] == words(facts)


@bdd_then("бриф тріажу без профілю, правил і фактів")
def brief_without_context(world: World) -> None:
    brief = brief_of(world)
    assert (brief.profile, brief.rules, brief.facts) == (None, None, None)


@bdd_then(
    rx(
        r'^профіль у брифі тріажу має ролі "(?P<roles>[^"]*)" і мінімальну зарплату (?P<salary>\d+)$'
    )
)
def brief_profile(world: World, roles: str, salary: str) -> None:
    profile = brief_of(world).profile
    assert profile is not None
    target = profile.target
    assert list(target.roles) == words(roles)
    assert target.min_salary_eur == int(salary)


@bdd_then("профіль у брифі тріажу порожній")
def brief_profile_empty(world: World) -> None:
    profile = brief_of(world).profile
    assert profile is not None
    assert (profile.target.roles, profile.target.min_salary_eur) == ((), None)


@bdd_then("правила тріажу з каталогу промптів")
def brief_rules(world: World) -> None:
    assert brief_of(world).rules == TRIAGE_RULES


# --- збереження тріажу ------------------------------------------------------------------------


def items_of(text: str) -> list[TriageInput]:
    items = []
    for part in text.split(";"):
        found = ITEM.match(part)
        assert found is not None, part
        number, score, verdict, reason = found.groups()
        items.append(
            TriageInput(
                job_number=int(number),
                score=int(score),
                verdict=verdict,
                reason=reason,
            )
        )
    return items


@action(r"^я (?:зберігаю|зберіг) тріаж: (?P<items>.*)$")
def save_triage(world: World, items: str) -> None:
    world.save_triage(items_of(items))


@bdd_when(rx(r"^я зберігаю тріаж із причиною з (?P<length>\d+) символ\w+$"))
def save_triage_reason_length(world: World, length: str) -> None:
    world.save_triage(
        [TriageInput(job_number=1, score=50, verdict="maybe", reason="r" * int(length))]
    )


@bdd_when("я зберігаю порожню пачку тріажу")
def save_empty_triage(world: World) -> None:
    world.save_triage([])


@bdd_when(rx(r"^я зберігаю тріаж для вакансій з (?P<first>\d+) по (?P<last>\d+)$"))
def save_triage_range(world: World, first: str, last: str) -> None:
    world.save_triage(
        [
            TriageInput(job_number=number, score=50, verdict="maybe", reason="ok")
            for number in range(int(first), int(last) + 1)
        ]
    )


@bdd_then("тріаж збережено без помилки")
def triage_saved(world: World) -> None:
    assert world.error is None, world.error
    assert world.saved_triage is not None


@bdd_then(rx(r'^збережено тріаж: "(?P<items>[^"]*)"$'))
def triage_result(world: World, items: str) -> None:
    assert world.error is None, world.error
    assert world.saved_triage is not None
    shown = [
        f"{item.job_number}:{item.score}:{item.verdict.value}:{item.reason}"
        for item in world.saved_triage.saved
    ]
    assert shown == [part.strip() for part in items.split(";")]


@bdd_then(
    rx(r'^вердикт (?P<verdict>analyse|maybe|skip) мають вакансії "(?P<numbers>[^"]*)"$')
)
def triage_verdict_ids(world: World, verdict: str, numbers: str) -> None:
    assert world.error is None, world.error
    assert world.saved_triage is not None
    found = world.saved_triage.with_verdict(TriageVerdict(verdict))
    assert found == [int(part) for part in words(numbers.replace(";", "; "))]


@bdd_then(
    rx(
        r'^вакансія (?P<number>\d+) має тріаж: скор (?P<score>\d+), вердикт "(?P<verdict>[^"]*)", '
        r'причина "(?P<reason>[^"]*)"$'
    )
)
def job_triage(
    world: World, number: str, score: int, verdict: str, reason: str
) -> None:
    triage = world.triage_of(int(number))
    assert triage is not None, "тріажу нема"
    assert (triage.score, triage.verdict.value, triage.reason) == (
        int(score),
        verdict,
        reason,
    )


@bdd_then(rx(r"^вакансія (?P<number>\d+) без тріажу$"))
def job_without_triage(world: World, number: str) -> None:
    assert world.triage_of(int(number)) is None


@bdd_then(rx(r'^вакансія (?P<number>\d+) протріажована "(?P<moment>[^"]*)"$'))
def triaged_at(world: World, number: str, moment: str) -> None:
    triage = world.triage_of(int(number))
    assert triage is not None
    assert triage.triaged_at.isoformat() == moment


# --- бриф аналізу ------------------------------------------------------------------------------


@bdd_when(rx(r"^я готую бриф аналізу вакансії (?P<number>\d+)$"))
def prepare_analysis(world: World, number: str) -> None:
    world.analysis_brief = world.attempt(
        lambda: world.analysis.prepare_analysis(world.actor, int(number))
    )


def analysis_brief(world: World) -> AnalysisBriefData:
    assert world.error is None, world.error
    assert world.analysis_brief is not None, "бриф аналізу не готували"
    return world.analysis_brief


@bdd_then(
    rx(
        r'^у брифі аналізу вакансія "(?P<title>[^"]*)" компанії "(?P<company>[^"]*)" з текстом "(?P<text>[^"]*)"$'
    )
)
def analysis_brief_job(world: World, title: str, company: str, text: str) -> None:
    job = analysis_brief(world).job
    assert (job.title, job.company, job.text) == (title, company, text)


@bdd_then(rx(r'^факти в брифі аналізу за порядком: "(?P<texts>[^"]*)"$'))
def analysis_brief_facts(world: World, texts: str) -> None:
    assert [fact.text for fact in analysis_brief(world).confirmed_facts] == words(texts)


@bdd_then("фактів у брифі аналізу немає")
def analysis_brief_no_facts(world: World) -> None:
    assert analysis_brief(world).confirmed_facts == ()


@bdd_then("профіль у брифі аналізу порожній")
def analysis_brief_empty_profile(world: World) -> None:
    assert analysis_brief(world).profile.target.roles == ()


@bdd_then(rx(r'^профіль у брифі аналізу має ролі "(?P<roles>[^"]*)"$'))
def analysis_brief_roles(world: World, roles: str) -> None:
    assert list(analysis_brief(world).profile.target.roles) == words(roles)


@bdd_then(rx(r'^рубрика: "(?P<text>[^"]*)"$'))
def rubric(world: World, text: str) -> None:
    assert analysis_brief(world).rubric == text


@bdd_then("у рубриці нема незаповнених плейсхолдерів")
def rubric_filled(world: World) -> None:
    text = analysis_brief(world).rubric
    assert "{" not in text
    assert "}" not in text


@bdd_then("попереднього аналізу в брифі нема")
def no_previous(world: World) -> None:
    assert analysis_brief(world).previous is None


@bdd_then(rx(r"^попередній аналіз у брифі має скор (?P<score>\d+)$"))
def previous_score(world: World, score: str) -> None:
    previous = analysis_brief(world).previous
    assert previous is not None
    assert previous.score == int(score)


# --- чернетка й збереження аналізу -----------------------------------------------------------


@setup(r'^у чернетці аналізу поле "(?P<name>[^"]*)" — "(?P<value>[^"]*)"$')
def draft_field(world: World, name: str, value: str) -> None:
    world.draft[name] = value


@setup(r"^у чернетці аналізу підсумок із (?P<length>\d+) символ\w+$")
def draft_summary_length(world: World, length: str) -> None:
    world.draft["summary"] = "s" * int(length)


@setup(rx(r'^у чернетці аналізу пункт "(?P<name>[^"]*)" із (?P<length>\d+) символ\w+$'))
def draft_item_length(world: World, name: str, length: str) -> None:
    world.draft[name] = "i" * int(length)


@setup(r'^у чернетці аналізу (?P<count>\d+) пункт\w* у полі "(?P<name>[^"]*)"$')
def draft_item_count(world: World, count: str, name: str) -> None:
    world.draft[name] = "; ".join(f"пункт {number}" for number in range(int(count)))


@setup(
    rx(
        r'^у чернетці аналізу прогалина "(?P<gap>[^"]*)" з питанням "(?P<question>[^"]*)"$'
    )
)
def draft_gap(world: World, gap: str, question: str) -> None:
    world.draft_gaps.append(GapInput(gap=gap, question=question))


@setup(rx(r'^у чернетці аналізу прогалина "(?P<gap>[^"]*)" без питання$'))
def draft_gap_without_question(world: World, gap: str) -> None:
    world.draft_gaps.append(GapInput(gap=gap))


@setup(
    rx(
        r'^у чернетці аналізу прогалина "(?P<gap>[^"]*)" з питанням із (?P<length>\d+) символ\w+$'
    )
)
def draft_gap_question_length(world: World, gap: str, length: str) -> None:
    world.draft_gaps.append(GapInput(gap=gap, question="q" * int(length)))


@bdd_then(
    rx(
        r'^прогалина (?P<place>\d+) аналізу вакансії (?P<number>\d+): "(?P<gap>[^"]*)" з питанням "(?P<question>[^"]*)"$'
    )
)
def analysis_gap(
    world: World, place: str, number: str, gap: str, question: str
) -> None:
    saved = world.analysis_of(int(number)).gaps[int(place) - 1]
    assert (saved.number, saved.gap, saved.question) == (int(place), gap, question)


@bdd_then(
    rx(
        r'^прогалина (?P<place>\d+) аналізу вакансії (?P<number>\d+): "(?P<gap>[^"]*)" без питання$'
    )
)
def analysis_gap_without_question(
    world: World, place: str, number: str, gap: str
) -> None:
    saved = world.analysis_of(int(number)).gaps[int(place) - 1]
    assert (saved.number, saved.gap, saved.question) == (int(place), gap, None)


@bdd_then(rx(r"^у аналізі вакансії (?P<number>\d+) прогалин: (?P<count>\d+)$"))
def analysis_gap_count(world: World, number: str, count: str) -> None:
    assert len(world.analysis_of(int(number)).gaps) == int(count)


@action(
    r"^я (?:аналізую|проаналізував) вакансію (?P<number>\d+) зі скором (?P<score>-?\d+)$"
)
def analyse(world: World, number: str, score: str) -> None:
    world.analyse(int(number), int(score))


@bdd_then("аналіз збережено без помилки")
def analysis_saved(world: World) -> None:
    assert world.error is None, world.error


@bdd_then(
    rx(
        r'^аналіз вакансії (?P<number>\d+): скор (?P<score>\d+), підсумок "(?P<summary>[^"]*)"$'
    )
)
def analysis_is(world: World, number: str, score: str, summary: str) -> None:
    analysis = world.analysis_of(int(number))
    assert (analysis.score, analysis.summary) == (int(score), summary)


@bdd_then(
    rx(
        r'^поле "(?P<name>[^"]*)" аналізу вакансії (?P<number>\d+) — "(?P<value>[^"]*)"$'
    )
)
def analysis_field(world: World, name: str, number: str, value: str) -> None:
    names = {"relocation": "relocation", "summary": "summary"}
    assert world.field(int(number), names.get(name, name)) == value


@bdd_then(rx(r'^аналіз вакансії (?P<number>\d+) збережено "(?P<moment>[^"]*)"$'))
def analysis_saved_at(world: World, number: str, moment: str) -> None:
    assert world.analysis_of(int(number)).updated_at.isoformat() == moment


@bdd_then(rx(r"^вакансія (?P<number>\d+) без аналізу$"))
def job_without_analysis(world: World, number: str) -> None:
    world.attempt(lambda: world.analysis.get_analysis(world.actor, int(number)))
    assert world.error is not None
    assert world.error.code == "not_found"


@bdd_then("фільтри пройдено")
def filters_passed(world: World) -> None:
    analysis = world.analysis_of(world.last_job)
    assert (analysis.filters_passed, analysis.flags) == (True, ())


@bdd_then(rx(r'^фільтри не пройдено, позначки: "(?P<flags>[^"]*)"$'))
def filters_failed(world: World, flags: str) -> None:
    analysis = world.analysis_of(world.last_job)
    assert analysis.filters_passed is False
    assert list(analysis.flags) == [part.strip() for part in flags.split("|")]


# --- застарілість ---------------------------------------------------------------------------


@bdd_then(rx(r"^аналіз вакансії (?P<number>\d+) не застарілий$"))
def analysis_fresh(world: World, number: str) -> None:
    assert world.analysis_of(int(number)).stale_since is None


@bdd_given(rx(r'^аналіз вакансії (?P<number>\d+) застарів із "(?P<moment>[^"]*)"$'))
@bdd_then(rx(r'^аналіз вакансії (?P<number>\d+) застарів із "(?P<moment>[^"]*)"$'))
def analysis_stale(world: World, number: str, moment: str) -> None:
    stale = world.analysis_of(int(number)).stale_since
    assert stale is not None, "аналіз не застарілий"
    assert stale.isoformat() == moment


# --- список -------------------------------------------------------------------------------------


@bdd_when("я переглядаю список")
def list_all(world: World) -> None:
    world.search()


@bdd_when("я переглядаю список схованих")
def list_hidden(world: World) -> None:
    world.search(dismissed=True)


@bdd_when(rx(r'^я переглядаю список із вердиктом "(?P<verdict>[^"]*)"$'))
def list_by_verdict(world: World, verdict: str) -> None:
    world.search(triage_verdict=verdict)


@bdd_when(rx(r'^я переглядаю список із форматом "(?P<mode>[^"]*)"$'))
def list_by_mode(world: World, mode: str) -> None:
    world.search(work_mode=mode)


@bdd_when(
    rx(
        r'^я переглядаю список із вердиктом "(?P<verdict>[^"]*)" і форматом "(?P<mode>[^"]*)"$'
    )
)
def list_by_verdict_and_mode(world: World, verdict: str, mode: str) -> None:
    world.search(triage_verdict=verdict, work_mode=mode)


@bdd_then(rx(r'^порядок у списку: "(?P<titles>[^"]*)"$'))
def list_order(world: World, titles: str) -> None:
    assert [item.title or "" for item in world.current_list()] == words(titles)


@bdd_then("список порожній")
def list_empty(world: World) -> None:
    assert world.current_list() == []


@bdd_then(
    rx(
        r'^у рядку вакансії "(?P<title>[^"]*)": скор тріажу (?P<score>\d+), вердикт "(?P<verdict>[^"]*)", '
        r'причина "(?P<reason>[^"]*)"$'
    )
)
def row_triage(world: World, title: str, score: str, verdict: str, reason: str) -> None:
    row = world.row(title)
    assert row.triage_score == int(score)
    assert row.triage_verdict is not None
    assert row.triage_verdict.value == verdict
    assert row.triage_reason == reason


@bdd_then(rx(r'^у рядку вакансії "(?P<title>[^"]*)" тріажу нема$'))
def row_without_triage(world: World, title: str) -> None:
    row = world.row(title)
    assert (row.triage_score, row.triage_verdict, row.triage_reason) == (
        None,
        None,
        None,
    )


@bdd_then(
    rx(
        r'^у рядку вакансії "(?P<title>[^"]*)": скор аналізу (?P<score>\d+), '
        r'фільтри пройдено "(?P<passed>так|ні)", формат "(?P<mode>[^"]*)"$'
    )
)
def row_analysis(world: World, title: str, score: str, passed: str, mode: str) -> None:
    row = world.row(title)
    assert row.score == int(score)
    assert row.filters_passed is (passed == "так")
    assert (row.work_mode.value if row.work_mode else "") == mode


@bdd_then(rx(r'^у рядку вакансії "(?P<title>[^"]*)" аналізу нема$'))
def row_without_analysis(world: World, title: str) -> None:
    row = world.row(title)
    assert (row.score, row.filters_passed, row.work_mode) == (None, None, None)


# --- помилки ------------------------------------------------------------------------------------


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)"$'))
def error_code(world: World, code: str) -> None:
    assert world.error is not None, "помилки не було"
    assert world.error.code == code


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def error_message(world: World, code: str, message: str) -> None:
    assert world.error is not None, "помилки не було"
    assert (world.error.code, world.error.message) == (code, message)


@bdd_then(
    rx(
        r'^отримую помилку "(?P<code>[^"]*)" для поля "(?P<field>[^"]*)" з текстом "(?P<message>[^"]*)"$'
    )
)
def error_field_message(world: World, code: str, field: str, message: str) -> None:
    error = world.error
    assert isinstance(error, InvalidValue), error
    assert (error.code, error.field, error.message) == (code, field, message)
    if isinstance(error, InvalidFields):
        assert error.problems[0].field == field
