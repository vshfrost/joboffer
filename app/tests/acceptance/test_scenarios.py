"""Кроки для features/scenarios.feature: `get_scenario` через реальні use cases вакансій і аналізу.

Вакансії, аналіз і відповіді на прогалини — справжні `JobUseCases` і `AnalysisUseCases` з in-memory
адаптерами; промпти — справжній каталог `prompts/` під `ScenarioPrompts` (хвіст «наступний крок»).
Каталог читається один раз при імпорті модуля: у тестах файлову систему вже заборонено.
"""

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
from application.contracts.actor import Actor, Channel, Scope
from application.contracts.analysis import AnalysisInput, GapAnswerInput, GapInput
from application.contracts.facts import FactInput
from application.contracts.jobs import JobInput
from application.contracts.scenarios import ScenarioData
from application.jobs.use_cases import JobUseCases
from application.ports.prompts import PromptKey
from application.scenarios.prompts import ScenarioPrompts
from application.scenarios.use_cases import ScenarioUseCases
from domain.identity.ids import UserId
from domain.shared.errors import DomainError, InvalidValue
from infrastructure.prompts.catalog import FilePrompts
from tests.support.analysis import InMemoryAnalysisUnitOfWork
from tests.support.clock import FakeClock
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store

scenarios("features/scenarios.feature")


PROMPTS = ScenarioPrompts(
    FilePrompts.load(Path(__file__).resolve().parents[2] / "prompts")
)
WALK_LIMIT = 20


def rx(pattern: str) -> Any:
    return parsers.re(pattern)


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        jobs_store = Store.empty()
        facts_store = FactStore.empty()
        profiles: dict[Any, Any] = {}
        inputs_changed: dict[Any, Any] = {}
        self.jobs = JobUseCases(lambda: InMemoryJobUnitOfWork(jobs_store), clock, ids)
        self.analysis = AnalysisUseCases(
            lambda: InMemoryAnalysisUnitOfWork(
                jobs_store, facts_store, profiles, inputs_changed
            ),
            clock,
            ids,
            PROMPTS,
        )
        self.scenarios = ScenarioUseCases(self.jobs, self.analysis, PROMPTS)
        self.actors: dict[str, Actor] = {}
        self.current = ""
        self.error: DomainError | None = None
        self.result: ScenarioData | None = None
        self.walk: list[ScenarioData] = []

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

    def ask(self, name: str, job: int | None) -> None:
        self.error = None
        self.result = None
        try:
            self.result = self.portal.call(
                self.scenarios.get_scenario, self.actor, name, job
            )
        except DomainError as error:
            self.error = error

    def walk_from(self, name: str, job: int) -> None:
        """Іде ланцюжком так, як його веде сервер: кожен наступний крок — це `next` попереднього."""
        self.walk = []
        step: str | None = name
        while step is not None:
            assert len(self.walk) < WALK_LIMIT, "ланцюжок не закінчується"
            self.ask(step, job)
            self.walk.append(self.got())
            step = self.walk[-1].next

    def got(self) -> ScenarioData:
        assert self.error is None, self.error
        assert self.result is not None, "get_scenario не викликано"
        return self.result


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@bdd_given(rx(r"^минає (?P<hours>\d+) год (?P<minutes>\d+) хв$"))
def time_passes(world: World, hours: str, minutes: str) -> None:
    world.clock.advance(timedelta(hours=int(hours), minutes=int(minutes)))


@bdd_given(rx(r'^є вакансія "(?P<title>[^"]*)" з текстом "(?P<text>[^"]*)"$'))
def job_with_text(world: World, title: str, text: str) -> None:
    data = JobInput(text=text, title=title, company="Acme")
    world.portal.call(world.jobs.add_job, world.actor, data)


@bdd_given("є проаналізована вакансія з двома відкритими прогалинами")
def analysed_job_with_gaps(world: World) -> None:
    job_with_text(world, "Backend", "Backend на Python та Go. Remote.")
    data = AnalysisInput(
        score=70,
        summary="Підсумок.",
        gaps=[
            GapInput(gap="Немає Go", question="Чи є досвід з Go?"),
            GapInput(gap="Немає Kubernetes", question="Чи працювали з Kubernetes?"),
        ],
    )
    world.portal.call(world.analysis.save_analysis, world.actor, 1, data)


@bdd_given(
    rx(
        r'^я відповідаю "(?P<answer>так|ні)" на прогалину (?P<gap>\d+) вакансії (?P<job>\d+)'
        r"(?: з фактами (?P<facts>.+))?$"
    )
)
def answer_gap(
    world: World, answer: str, gap: str, job: str, facts: str | None
) -> None:
    texts = [] if facts is None else [facts.split('"')[1]]
    data = GapAnswerInput(
        has_experience=answer == "так",
        facts=[FactInput(kind="experience", text=text) for text in texts],
    )
    world.portal.call(world.analysis.answer_gap, world.actor, int(job), int(gap), data)


@bdd_when(rx(r'^я прошу сценарій "(?P<name>[^"]*)" без вакансії$'))
def ask_without_job(world: World, name: str) -> None:
    world.ask(name, None)


@bdd_when(rx(r'^я прошу сценарій "(?P<name>[^"]*)" для вакансії (?P<job>\d+)$'))
@bdd_then(rx(r'^я прошу сценарій "(?P<name>[^"]*)" для вакансії (?P<job>\d+)$'))
def ask_for_job(world: World, name: str, job: str) -> None:
    world.ask(name, int(job))


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)"$'))
def error_code(world: World, code: str) -> None:
    assert world.error is not None, "помилки не було"
    assert world.error.code == code


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" для поля "(?P<field>[^"]*)"$'))
def error_field(world: World, code: str, field: str) -> None:
    error = world.error
    assert isinstance(error, InvalidValue), error
    assert (error.code, error.field) == (code, field)


@bdd_then(rx(r'^текст помилки називає сценарії "(?P<names>[^"]*)"$'))
def error_names(world: World, names: str) -> None:
    assert world.error is not None, "помилки не було"
    for name in names.split(";"):
        assert name in world.error.message


@bdd_then(rx(r'^сценарій "(?P<name>[^"]*)" має наступний "(?P<following>[^"]*)"$'))
def next_is(world: World, name: str, following: str) -> None:
    result = world.got()
    assert (result.name, result.next) == (name, following)


@bdd_then("наступного кроку нема")
def no_next(world: World) -> None:
    assert world.got().next is None


@bdd_then("сценарій не пропущений")
def not_skipped(world: World) -> None:
    assert world.got().skip_reason is None


@bdd_then(rx(r'^сценарій пропущений з причиною "(?P<reason>[^"]*)"$'))
def skipped(world: World, reason: str) -> None:
    assert world.got().skip_reason == reason


@bdd_then(rx(r'^промпт сценарію містить "(?P<part>[^"]*)"$'))
def prompt_has(world: World, part: str) -> None:
    assert part in world.got().prompt


@bdd_then(rx(r'^промпт сценарію не містить "(?P<part>[^"]*)"$'))
def prompt_has_not(world: World, part: str) -> None:
    assert part not in world.got().prompt


@bdd_when(rx(r'^я йду ланцюжком від "(?P<name>[^"]*)" для вакансії (?P<job>\d+)$'))
def walk_chain(world: World, name: str, job: str) -> None:
    world.walk_from(name, int(job))


@bdd_then(rx(r'^пройдені кроки: "(?P<names>[^"]*)"$'))
def walked_steps(world: World, names: str) -> None:
    assert [step.name for step in world.walk] == names.split(";")


@bdd_then("жоден пройдений крок не пропущений")
def walk_without_skips(world: World) -> None:
    assert [step.skip_reason for step in world.walk] == [None] * len(world.walk)


@bdd_then(rx(r"^промпт сценарію закінчується реченням про наступний крок$"))
def prompt_ends_with_tail(world: World) -> None:
    tail = PROMPTS.get(PromptKey.SCENARIO_NEXT_STEP)
    assert "get_scenario" in tail
    assert "next" in tail
    assert world.got().prompt.endswith(tail)


@bdd_then("промпт сценарію не містить речення про наступний крок")
def prompt_without_tail(world: World) -> None:
    assert PROMPTS.get(PromptKey.SCENARIO_NEXT_STEP) not in world.got().prompt


@bdd_then(rx(r'^у промпті сценарію "(?P<first>[^"]*)" передує "(?P<second>[^"]*)"$'))
def prompt_order(world: World, first: str, second: str) -> None:
    prompt = world.got().prompt.lower()
    assert first.lower() in prompt, first
    assert second.lower() in prompt, second
    assert prompt.index(first.lower()) < prompt.index(second.lower())
