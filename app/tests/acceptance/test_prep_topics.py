"""Кроки для features/prep_topics.feature: use cases тем підготовки, вакансій, аналізу й подач +
in-memory адаптери через портал.

Усі значення в кроках — у лапках і можуть бути порожніми, тому кроки — регулярні вирази з
іменованими групами. «Припустимо я зберіг …» і «Якщо я зберігаю …» — один і той самий крок; у
«Припустимо» додатково перевіряється, що дія вдалася. Вакансія й тема — за номером на
користувача; внутрішній UUID у сценаріях не фігурує. Довгі значення для перевірки меж пишуться
як `а×120` (символ, «×», кількість), а перенос рядка в значенні — як `\\n`.
"""

import functools
import re
from collections.abc import Callable
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
from application.contracts.analysis import AnalysisInput
from application.contracts.applications import ApplicationInput
from application.contracts.jobs import JobInput
from application.contracts.prep import TopicData, TopicInput, TopicsBriefData
from application.jobs.use_cases import JobUseCases
from application.ports.prompts import PromptKey
from application.prep.use_cases import PrepUseCases
from domain.identity.ids import UserId
from domain.prep.topic import TopicStatus
from domain.shared.errors import DomainError
from tests.support.analysis import InMemoryAnalysisUnitOfWork
from tests.support.applications import InMemoryApplicationUnitOfWork
from tests.support.clock import FakeClock
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store
from tests.support.prep import InMemoryPrepUnitOfWork, PrepStore

scenarios("features/prep_topics.feature")

Step = Callable[..., Any]

RULES = "Propose topics for the gaps. Then call save_prep_topics."
REPEATED = re.compile(r"(\S)×(\d+)")


class FakePrompts:
    def get(self, key: PromptKey) -> str:
        return {PromptKey.PREP_TOPIC_RULES: RULES}[key]


def rx(pattern: str) -> Any:
    return parsers.re(pattern)


def text(value: str) -> str:
    """`а×120` → 120 символів «а»; `\\n` → перенос рядка."""
    return REPEATED.sub(lambda m: m[1] * int(m[2]), value).replace("\\n", "\n")


def words(value: str) -> list[str]:
    return [] if value.strip() == "" else [part.strip() for part in value.split(";")]


def succeeded(step: Step) -> Step:
    """Крок-передумова: дія має вдатися, інакше сценарій не про те."""

    @functools.wraps(step)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        step(*args, **kwargs)
        world: World = kwargs["world"]
        assert world.error is None, world.error

    return wrapper


def action(pattern: str) -> Callable[[Step], Step]:
    """Один текст — і «Припустимо я зробив …», і «Якщо я роблю …»."""

    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(succeeded(step))
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.jobs_store = Store.empty()
        self.prep_store = PrepStore.empty()
        self.jobs = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.jobs_store), clock, ids
        )
        self.applications = ApplicationUseCases(
            lambda: InMemoryApplicationUnitOfWork(self.jobs_store), clock
        )
        self.analysis = AnalysisUseCases(
            lambda: InMemoryAnalysisUnitOfWork(
                self.jobs_store, FactStore.empty(), {}, {}
            ),
            clock,
            ids,
            FakePrompts(),
        )
        self.prep = PrepUseCases(
            lambda: InMemoryPrepUnitOfWork(self.jobs_store, self.prep_store),
            clock,
            ids,
            FakePrompts(),
        )
        self.actors: dict[str, Actor] = {}
        self.current = ""
        self.error: DomainError | None = None
        self.brief: TopicsBriefData | None = None
        self.saved: list[TopicData] | None = None
        self.listed: list[TopicData] | None = None

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
        self.reset_outcome()

    @property
    def actor(self) -> Actor:
        return self.actors[self.current]

    def reset_outcome(self) -> None:
        self.error = None
        self.brief = None
        self.saved = None
        self.listed = None

    def attempt(self, call: Callable[[], Any]) -> Any:
        """Виконує дію; помилка домену запамʼятовується для кроків «Тоді»."""
        self.reset_outcome()
        try:
            return self.portal.call(call)
        except DomainError as error:
            self.error = error
            return None

    # --- вакансії й аналіз ---------------------------------------------------------------------

    def add_job(self, title: str, company: str) -> None:
        data = JobInput(text=f"Опис вакансії {title}", title=title, company=company)
        self.attempt(lambda: self.jobs.add_job(self.actor, data))
        assert self.error is None, self.error

    def analyse(self, number: int, score: int, gaps: list[str]) -> None:
        data = AnalysisInput(score=score, summary="Підсумок.", gaps=gaps)
        self.attempt(lambda: self.analysis.save_analysis(self.actor, number, data))
        assert self.error is None, self.error

    # --- теми ----------------------------------------------------------------------------------

    def save(self, job: int, items: list[TopicInput]) -> None:
        self.saved = self.attempt(
            lambda: self.prep.save_prep_topics(self.actor, job, items)
        )

    def topics(self) -> list[TopicData]:
        return self.portal.call(self.prep.list_prep_topics, self.actor)

    def topic(self, slug: str) -> TopicData:
        found = [topic for topic in self.topics() if topic.slug == slug]
        assert len(found) == 1, (slug, found)
        return found[0]

    def shown_brief(self) -> TopicsBriefData:
        assert self.error is None, self.error
        assert self.brief is not None, "бриф не готували"
        return self.brief


def item(slug: str, gap: str = "Прогалина", **fields: str) -> TopicInput:
    return TopicInput(
        slug=text(slug),
        title=text(fields.get("title", f"Тема {slug}")),
        kind=fields.get("kind", "tech"),
        gap=text(gap),
        summary=text(fields.get("summary", "")),
        deadline=text(fields.get("deadline", "")),
    )


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


# --- хто я, передумови -----------------------------------------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_given(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@bdd_given(
    rx(
        r'^є проаналізована вакансія "(?P<title>[^"]*)"(?: компанії "(?P<company>[^"]*)")?'
        r' зі скором (?P<score>\d+)(?: і прогалинами "(?P<gaps>[^"]*)")?$'
    )
)
@bdd_when(
    rx(
        r'^є проаналізована вакансія "(?P<title>[^"]*)"(?: компанії "(?P<company>[^"]*)")?'
        r' зі скором (?P<score>\d+)(?: і прогалинами "(?P<gaps>[^"]*)")?$'
    )
)
def analysed_job(
    world: World, title: str, company: str | None, score: str, gaps: str | None
) -> None:
    world.add_job(title, company or "")
    number = len(
        [key for key in world.jobs_store.jobs if key[0] == world.actor.user_id]
    )
    world.analyse(number, int(score), words(gaps or ""))


@bdd_given(rx(r'^є вакансія "(?P<title>[^"]*)" без аналізу$'))
def raw_job(world: World, title: str) -> None:
    world.add_job(title, "")


@bdd_given(
    rx(r"^я перезбережаю аналіз вакансії (?P<number>\d+) зі скором (?P<score>\d+)$")
)
@bdd_when(
    rx(r"^я перезбережаю аналіз вакансії (?P<number>\d+) зі скором (?P<score>\d+)$")
)
def reanalyse(world: World, number: str, score: str) -> None:
    world.analyse(int(number), int(score), [])


@bdd_when(rx(r"^я ховаю вакансію (?P<number>\d+)$"))
def dismiss(world: World, number: str) -> None:
    world.attempt(
        lambda: world.jobs.dismiss_jobs(world.actor, [int(number)], "не цікаво")
    )
    assert world.error is None, world.error


@bdd_when(rx(r"^я подався на вакансію (?P<number>\d+)$"))
def apply_to(world: World, number: str) -> None:
    data = ApplicationInput(channel="email")
    world.attempt(
        lambda: world.applications.mark_applied(world.actor, int(number), data)
    )
    assert world.error is None, world.error


@bdd_when(rx(r"^подачу на вакансію (?P<number>\d+) закрито відмовою$"))
def reject_application(world: World, number: str) -> None:
    world.attempt(
        lambda: world.applications.set_application_status(
            world.actor, int(number), "rejected"
        )
    )
    assert world.error is None, world.error


# --- бриф ------------------------------------------------------------------------------------


@bdd_when(rx(r"^я готую теми для вакансії (?P<number>\d+)$"))
def prepare(world: World, number: str) -> None:
    world.brief = world.attempt(
        lambda: world.prep.prepare_prep_topics(world.actor, int(number))
    )


@bdd_then(rx(r'^у брифі вакансія "(?P<title>[^"]*)" компанії "(?P<company>[^"]*)"$'))
def brief_job(world: World, title: str, company: str) -> None:
    job = world.shown_brief().job
    assert (job.title, job.company) == (title, company)


@bdd_then(
    rx(r'^у брифі аналіз зі скором (?P<score>\d+) і прогалинами "(?P<gaps>[^"]*)"$')
)
def brief_analysis(world: World, score: str, gaps: str) -> None:
    analysis = world.shown_brief().analysis
    assert (analysis.score, [item.gap for item in analysis.gaps]) == (
        int(score),
        words(gaps),
    )


@bdd_then(rx(r"^у брифі тем немає$"))
def brief_without_topics(world: World) -> None:
    assert world.shown_brief().topics == ()


@bdd_then(rx(r'^у брифі теми за порядком: "(?P<slugs>[^"]*)"$'))
def brief_topics(world: World, slugs: str) -> None:
    assert [topic.slug for topic in world.shown_brief().topics] == words(slugs)


@bdd_then(rx(r'^правила в брифі: "(?P<rules>[^"]*)"$'))
def brief_rules(world: World, rules: str) -> None:
    assert world.shown_brief().rules == rules


# --- збереження ------------------------------------------------------------------------------


@action(
    r'^я (?:зберігаю|зберіг) тему "(?P<slug>[^"]*)" для вакансії (?P<job>\d+) з gap "(?P<gap>[^"]*)"$'
)
def save_short(world: World, slug: str, job: str, gap: str) -> None:
    world.save(int(job), [item(slug, gap)])


@action(
    r'^я (?:зберігаю|зберіг) тему для вакансії (?P<job>\d+): slug "(?P<slug>[^"]*)", назва "(?P<title>[^"]*)",'
    r' kind "(?P<kind>[^"]*)", gap "(?P<gap>[^"]*)", опис "(?P<summary>[^"]*)", дедлайн "(?P<deadline>[^"]*)"$'
)
def save_full(
    world: World,
    job: str,
    slug: str,
    title: str,
    kind: str,
    gap: str,
    summary: str,
    deadline: str,
) -> None:
    world.save(
        int(job),
        [item(slug, gap, title=title, kind=kind, summary=summary, deadline=deadline)],
    )


@bdd_given(rx(r"^я зберіг теми для вакансії (?P<job>\d+):$"))
@bdd_when(rx(r"^я зберігаю теми для вакансії (?P<job>\d+):$"))
def save_table(world: World, datatable: list[list[str]], job: str) -> None:
    items = [
        item(slug, gap, title=title, kind=kind, summary=summary, deadline=deadline)
        for slug, title, kind, gap, summary, deadline in datatable[1:]
    ]
    world.save(int(job), items)


@bdd_when(rx(r"^я зберігаю порожній список тем для вакансії (?P<job>\d+)$"))
def save_nothing(world: World, job: str) -> None:
    world.save(int(job), [])


@bdd_when(
    rx(r"^я зберігаю (?P<count>\d+) (?:тему|теми|тем) для вакансії (?P<job>\d+)$")
)
def save_many(world: World, count: str, job: str) -> None:
    world.save(int(job), [item(f"topic-{n}") for n in range(int(count))])


@bdd_when(rx(r"^я переглядаю теми$"))
def view_topics(world: World) -> None:
    world.listed = world.attempt(lambda: world.prep.list_prep_topics(world.actor))


# --- результат -------------------------------------------------------------------------------


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def error_message(world: World, code: str, message: str) -> None:
    assert world.error is not None, "помилки не було"
    assert (world.error.code, world.error.message) == (code, text(message))


@bdd_then(rx(r"^тем немає$"))
def no_topics(world: World) -> None:
    assert world.topics() == []


@bdd_then(rx(r"^тем (?P<count>\d+)$"))
def topic_count(world: World, count: str) -> None:
    assert world.error is None, world.error
    assert len(world.topics()) == int(count)


@bdd_then(rx(r'^збережено теми за порядком запиту: "(?P<slugs>[^"]*)"$'))
def saved_order(world: World, slugs: str) -> None:
    assert world.error is None, world.error
    assert world.saved is not None, "теми не зберігали"
    assert [topic.slug for topic in world.saved] == words(slugs)


@bdd_then(rx(r'^список тем за порядком: "(?P<slugs>[^"]*)"$'))
def listed_order(world: World, slugs: str) -> None:
    assert world.error is None, world.error
    assert world.listed is not None, "теми не переглядали"
    assert [topic.slug for topic in world.listed] == words(slugs)


@bdd_then(rx(r'^тема "(?P<slug>[^"]*)": (?P<fields>(?:[^\s"]+ "[^"]*"(?:, )?)+)$'))
def topic_fields(world: World, slug: str, fields: str) -> None:
    topic = world.topic(slug)
    shown = {
        "назва": topic.title,
        "kind": topic.kind.value,
        "опис": topic.summary,
        "дедлайн": "" if topic.deadline is None else topic.deadline.isoformat(),
    }
    expected = dict(re.findall(r'(\S+) "([^"]*)"', fields))
    assert {name: shown[name] for name in expected} == expected


@bdd_then(rx(r'^тема "(?P<slug>[^"]*)" прив\'язана до вакансій: "(?P<jobs>[^"]*)"$'))
def topic_jobs(world: World, slug: str, jobs: str) -> None:
    linked = [f"{job.job_number}: {job.gap}" for job in world.topic(slug).jobs]
    assert linked == words(jobs)


@bdd_then(rx(r'^тема "(?P<slug>[^"]*)" має пріоритет (?P<priority>\d+)$'))
def topic_priority(world: World, slug: str, priority: str) -> None:
    assert world.topic(slug).priority == int(priority)


@bdd_then(rx(r'^тема "(?P<slug>[^"]*)" має номер (?P<number>\d+)$'))
def topic_number(world: World, slug: str, number: str) -> None:
    assert world.topic(slug).topic_number == int(number)


@bdd_then(rx(r'^тема "(?P<slug>[^"]*)" нова: без кроків$'))
def topic_is_new(world: World, slug: str) -> None:
    topic = world.topic(slug)
    assert (topic.status, topic.steps_done, topic.steps_total, topic.minutes_left) == (
        TopicStatus.NEW,
        0,
        0,
        0,
    )
