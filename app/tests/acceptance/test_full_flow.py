"""Кроки для features/full_flow.feature: увесь шлях вакансії через справжні use cases.

Вакансії, аналіз, документи й подачі — справжні `JobUseCases`, `AnalysisUseCases`, `DocumentUseCases`,
`ApplicationUseCases` над одним in-memory сховищем; промпти — справжній каталог `prompts/`. Після кроку
«після кроку … наступний …» питаємо `get_scenario`. Агента грає тест: він сам викликає use cases замість
браузера й моделі, тож заповнення форми в реальному браузері тут не перевіряється — лише те, чим володіє
сервер (промпт подачі й `mark_applied`). Номер вакансії в сценаріях — 1, якщо крок не каже інакше.
"""

import functools
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.analysis.use_cases import AnalysisUseCases
from application.applications.use_cases import ApplicationUseCases
from application.contracts.actor import Actor, Channel, Scope
from application.contracts.analysis import AnalysisInput, GapAnswerInput, GapInput
from application.contracts.applications import ApplicationData, ApplicationInput
from application.contracts.documents import (
    ClaimData,
    CoverLetterData,
    CvData,
    CvEntryData,
    CvSectionData,
)
from application.contracts.facts import FactInput
from application.contracts.jobs import JobInput, JobSearchInput
from application.contracts.profile import ContactsData
from application.contracts.scenarios import ScenarioData
from application.documents.use_cases import DocumentUseCases
from application.jobs.use_cases import JobUseCases
from application.profile.use_cases import ProfileUseCases
from application.scenarios.prompts import ScenarioPrompts
from application.scenarios.use_cases import ScenarioUseCases
from domain.facts.fact import NewFact
from domain.facts.ids import FactId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.jobs.linkedin import linkedin_job_url
from domain.profile.profile import Profile
from domain.shared.errors import DomainError
from infrastructure.prompts.catalog import FilePrompts
from tests.support.analysis import InMemoryAnalysisUnitOfWork
from tests.support.applications import InMemoryApplicationUnitOfWork
from tests.support.clock import FakeClock
from tests.support.documents import DocumentStore, InMemoryDocumentUnitOfWork
from tests.support.facts import InMemoryFactUnitOfWork
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store
from tests.support.pdf import Shop
from tests.support.profile import InMemoryProfileUnitOfWork

scenarios("features/full_flow.feature")

Step = Callable[..., Any]

# Каталог читається один раз при імпорті: у тестах файлову систему вже заборонено.
PROMPTS = ScenarioPrompts(
    FilePrompts.load(Path(__file__).resolve().parents[2] / "prompts")
)
# Номер підтвердженого факту з передумови: на нього спираються всі документи.
BASE_FACT = 1


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


def action(pattern: str) -> Callable[[Step], Step]:
    """Один текст — і «Припустимо я зробив …», і «Якщо я роблю …» (`(?:зберігаю|зберіг)`)."""

    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(succeeded(step))
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


def words(text: str) -> list[str]:
    return [] if text.strip() == "" else [part.strip() for part in text.split(";")]


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.jobs_store = Store.empty()
        self.facts_store = FactStore.empty()
        self.docs_store = DocumentStore.empty()
        self.profiles: dict[UserId, Profile] = {}
        self.inputs_changed: dict[Any, Any] = {}
        self.jobs = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.jobs_store), clock, ids
        )
        self.analysis = AnalysisUseCases(
            lambda: InMemoryAnalysisUnitOfWork(
                self.jobs_store,
                self.facts_store,
                self.profiles,
                self.inputs_changed,
            ),
            clock,
            ids,
            PROMPTS,
        )
        self.documents = DocumentUseCases(
            lambda: InMemoryDocumentUnitOfWork(
                self.jobs_store, self.docs_store, self.facts_store, self.profiles
            ),
            clock,
            ids,
            PROMPTS,
            Shop().output(),
        )
        self.applications = ApplicationUseCases(
            lambda: InMemoryApplicationUnitOfWork(self.jobs_store, self.docs_store),
            clock,
        )
        self.profile = ProfileUseCases(
            lambda: InMemoryProfileUnitOfWork(self.profiles, {}, {}), clock
        )
        self.scenarios = ScenarioUseCases(self.jobs, self.analysis, PROMPTS)
        self.actors: dict[str, Actor] = {}
        self.current = ""
        self.error: DomainError | None = None
        self.scenario: ScenarioData | None = None

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
        self.current = name
        self.error = None

    @property
    def actor(self) -> Actor:
        return self.actors[self.current]

    def attempt(self, call: Callable[[], Any]) -> Any:
        """Виконує дію; помилка домену запамʼятовується для кроків «Тоді»."""
        self.error = None
        try:
            return self.portal.call(call)
        except DomainError as error:
            self.error = error
            return None

    def ask(self, name: str, job: int = 1) -> ScenarioData:
        """`get_scenario` для поточного користувача; результат лишається для кроків про промпт."""
        self.scenario = self.attempt(
            lambda: self.scenarios.get_scenario(self.actor, name, job)
        )
        return self.got()

    def got(self) -> ScenarioData:
        assert self.error is None, self.error
        assert self.scenario is not None, "get_scenario не викликано"
        return self.scenario

    def application(self, job: int = 1) -> ApplicationData | None:
        return self.portal.call(self.applications.get_application, self.actor, job)

    def documents_of(self, job: int) -> list[str]:
        found = self.portal.call(self.documents.list_documents, self.actor, job)
        return [item.kind.name.lower() for item in found]

    def seed_fact(self, text: str) -> None:
        async def add() -> None:
            async with InMemoryFactUnitOfWork(self.facts_store) as uow:
                added = await uow.facts.add(
                    self.actor.user_id,
                    FactId(self.ids.new()),
                    NewFact.parse(kind="experience", text=text),
                    self.clock.now(),
                )
                await uow.facts.confirm(
                    self.actor.user_id, [added.number], self.clock.now()
                )
                await uow.commit()

        self.portal.call(add)

    def seed_alert(self, title: str, linkedin_id: str) -> None:
        """Вакансія з листа-алерту LinkedIn без тексту: її створить B10, тут — передумова."""

        async def seed() -> None:
            async with InMemoryJobUnitOfWork(self.jobs_store) as uow:
                await uow.jobs.add(
                    self.actor.user_id,
                    JobId(self.ids.new()),
                    NewJob(
                        text=None,
                        url=linkedin_job_url(linkedin_id),
                        title=title,
                        company="Acme",
                        linkedin_id=linkedin_id,
                        source="linkedin_alert",
                    ),
                    self.clock.now(),
                )
                await uow.commit()

        self.portal.call(seed)

    def analyse(self, gaps: list[str]) -> None:
        data = AnalysisInput(
            score=70,
            summary="Підсумок.",
            gaps=[GapInput(gap=gap, question=f"Чи є досвід: {gap}?") for gap in gaps],
        )
        self.attempt(lambda: self.analysis.save_analysis(self.actor, 1, data))


def claim(text: str) -> ClaimData:
    return ClaimData(text=text, fact_ids=(BASE_FACT,))


def cv_data() -> CvData:
    entry = CvEntryData(
        heading=claim("Engineer · Acme"), bullets=[claim("Built payment service")]
    )
    return CvData(
        headline=claim("Senior Backend Engineer"),
        summary=claim("Payments backend engineer"),
        sections=[CvSectionData(name="Experience", entries=[entry])],
    )


def letter_data() -> CoverLetterData:
    text = "Dear team,\n\n" + " ".join(["word"] * 170) + "\n\nBest regards,\nAlex"
    return CoverLetterData(text=text, fact_ids=(BASE_FACT,))


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


# --- хто я, час, передумови -----------------------------------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@bdd_given(
    rx(
        r"^в профілі є ім'я \"(?P<name>[^\"]*)\""
        r' і підтверджений факт experience "(?P<fact>[^"]*)"$'
    )
)
def profile_ready(world: World, name: str, fact: str) -> None:
    data = ContactsData(full_name=name)
    world.attempt(lambda: world.profile.save_section(world.actor, data))
    assert world.error is None, world.error
    world.seed_fact(fact)


@bdd_given(
    rx(
        r'^є вакансія з листа-алерту "(?P<title>[^"]*)" з посиланням LinkedIn (?P<linkedin_id>\d+) без тексту$'
    )
)
def alert_job(world: World, title: str, linkedin_id: str) -> None:
    world.seed_alert(title, linkedin_id)


@bdd_given("є проаналізована вакансія 1 без прогалин")
def analysed_job(world: World) -> None:
    add_job(world, "Backend", "Backend на Python та Go. Remote.")
    assert world.error is None, world.error
    save_analysis(world, "")
    assert world.error is None, world.error


@bdd_given(rx(r"^минає (?P<hours>\d+) год (?P<minutes>\d+) хв$"))
@bdd_when(rx(r"^минає (?P<hours>\d+) год (?P<minutes>\d+) хв$"))
def time_passes(world: World, hours: str, minutes: str) -> None:
    world.clock.advance(timedelta(hours=int(hours), minutes=int(minutes)))


# --- кроки ланцюжка, які виконує «агент» -----------------------------------------------------


@action(r'^я (?:додаю|додав) вакансію "(?P<title>[^"]*)" з текстом "(?P<text>[^"]*)"$')
def add_job(world: World, title: str, text: str) -> None:
    data = JobInput(text=text, title=title, company="Acme")
    world.attempt(lambda: world.jobs.add_job(world.actor, data))


@bdd_when(
    rx(
        r'^я дописую текст "(?P<text>[^"]*)" до вакансії з посиланням LinkedIn (?P<linkedin_id>\d+)$'
    )
)
def add_text(world: World, text: str, linkedin_id: str) -> None:
    data = JobInput(text=text, url=linkedin_job_url(linkedin_id))
    world.attempt(lambda: world.jobs.add_job(world.actor, data))
    assert world.error is None, world.error


@action(r'^я (?:зберігаю|зберіг) аналіз вакансії 1 з прогалинами "(?P<gaps>[^"]*)"$')
def save_analysis(world: World, gaps: str) -> None:
    world.analyse(words(gaps))


@action(r"^я (?:зберігаю|зберіг) повторний аналіз вакансії 1$")
def save_reanalysis(world: World) -> None:
    world.analyse([])


@action(
    r'^я (?:відповідаю|відповів) "(?P<answer>так|ні)" на прогалину (?P<gap>\d+) вакансії (?P<job>\d+)'
    r'(?: з фактом "(?P<fact>[^"]*)")?$'
)
def answer_gap(world: World, answer: str, gap: str, job: str, fact: str | None) -> None:
    data = GapAnswerInput(
        has_experience=answer == "так",
        facts=[] if fact is None else [FactInput(kind="experience", text=fact)],
    )
    world.attempt(
        lambda: world.analysis.answer_gap(world.actor, int(job), int(gap), data)
    )


@action(r"^я (?:зберігаю|зберіг) CV вакансії (?P<job>\d+)$")
def save_cv(world: World, job: str) -> None:
    world.attempt(lambda: world.documents.save_cv(world.actor, int(job), cv_data()))


@action(r"^я (?:зберігаю|зберіг) супровідний лист вакансії (?P<job>\d+)$")
def save_letter(world: World, job: str) -> None:
    world.attempt(
        lambda: world.documents.save_cover_letter(world.actor, int(job), letter_data())
    )


@action(
    r'^я (?:позначаю|позначив) вакансію (?P<job>\d+) поданою каналом "(?P<channel>[^"]*)"$'
)
@bdd_when(
    rx(
        r'^я як користувач записую подачу на вакансію (?P<job>\d+) каналом "(?P<channel>[^"]*)"$'
    )
)
def mark_applied(world: World, job: str, channel: str) -> None:
    data = ApplicationInput(channel=channel)
    world.attempt(lambda: world.applications.mark_applied(world.actor, int(job), data))


@bdd_given(
    rx(r'^подачу на вакансію (?P<job>\d+) переведено у статус "(?P<status>[^"]*)"$')
)
def move_status(world: World, job: str, status: str) -> None:
    world.attempt(
        lambda: world.applications.set_application_status(world.actor, int(job), status)
    )
    assert world.error is None, world.error


@bdd_when(rx(r'^я прошу сценарій "(?P<name>[^"]*)" для вакансії (?P<job>\d+)$'))
def ask_scenario(world: World, name: str, job: str) -> None:
    world.scenario = world.attempt(
        lambda: world.scenarios.get_scenario(world.actor, name, int(job))
    )


@bdd_when(
    rx(
        r'^я відмовляюся від супровідного листа і прошу сценарій "(?P<name>[^"]*)" для вакансії (?P<job>\d+)$'
    )
)
def decline_letter(world: World, name: str, job: str) -> None:
    """Відмова — це відсутність виклику save_cover_letter: агент просто питає, що далі."""
    ask_scenario(world, name, job)


# --- перевірки -------------------------------------------------------------------------------


@bdd_then(rx(r'^після кроку "(?P<name>[^"]*)" наступний "(?P<following>[^"]*)"$'))
def next_after(world: World, name: str, following: str) -> None:
    assert world.ask(name).next == following


@bdd_then(rx(r'^сценарій "(?P<name>[^"]*)" має наступний "(?P<following>[^"]*)"$'))
def next_is(world: World, name: str, following: str) -> None:
    result = world.got()
    assert (result.name, result.next) == (name, following)


@bdd_then(rx(r'^після кроку "(?P<name>[^"]*)" наступного кроку нема$'))
def no_next(world: World, name: str) -> None:
    assert world.ask(name).next is None


@bdd_then(rx(r'^крок "(?P<name>[^"]*)" пропущений з причиною "(?P<reason>[^"]*)"$'))
def skipped(world: World, name: str, reason: str) -> None:
    assert world.ask(name).skip_reason == reason


@bdd_then("крок не пропущений")
def not_skipped(world: World) -> None:
    assert world.got().skip_reason is None


@bdd_then(rx(r'^промпт кроку містить "(?P<part>[^"]*)"$'))
def prompt_has(world: World, part: str) -> None:
    assert part in world.got().prompt


@bdd_then(rx(r'^у промпті кроку "(?P<first>[^"]*)" передує "(?P<second>[^"]*)"$'))
def prompt_order(world: World, first: str, second: str) -> None:
    prompt = world.got().prompt
    assert first in prompt, first
    assert second in prompt, second
    assert prompt.index(first) < prompt.index(second)


@bdd_then(rx(r"^аналіз вакансії 1 (?P<state>застарів|не застарів)$"))
def analysis_staleness(world: World, state: str) -> None:
    found = world.portal.call(world.analysis.get_analysis, world.actor, 1)
    assert (found.stale_since is not None) == (state == "застарів")


@bdd_then(rx(r"^вакансія (?P<job>\d+) (?P<state>потребує|не потребує) тексту$"))
def needs_text(world: World, job: str, state: str) -> None:
    found = world.portal.call(world.jobs.get_job, world.actor, int(job))
    assert found.needs_text == (state == "потребує")


@bdd_then(rx(r'^для вакансії (?P<job>\d+) збережено документи: "(?P<kinds>[^"]*)"$'))
def saved_documents(world: World, job: str, kinds: str) -> None:
    assert world.documents_of(int(job)) == words(kinds)


@bdd_then(
    rx(
        r'^вакансія (?P<job>\d+) має подачу зі статусом "(?P<status>[^"]*)" і каналом "(?P<channel>[^"]*)"$'
    )
)
def has_application(world: World, job: str, status: str, channel: str) -> None:
    assert world.error is None, world.error
    found = world.application(int(job))
    assert found is not None, "подачі нема"
    assert (found.status.value, found.channel.value) == (status, channel)


@bdd_then(rx(r"^подачі на вакансію (?P<job>\d+) ще нема$"))
def no_application(world: World, job: str) -> None:
    assert world.application(int(job)) is None


@bdd_then(rx(r"^поданих вакансій у списку: (?P<count>\d+)$"))
def applied_count(world: World, count: str) -> None:
    found = world.portal.call(
        world.jobs.list_jobs, world.actor, JobSearchInput(status="applied")
    )
    assert len(found) == int(count)


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)"$'))
def error_code(world: World, code: str) -> None:
    assert world.error is not None, "помилки не було"
    assert world.error.code == code
