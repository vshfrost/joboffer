"""Кроки для features/gaps_answer.feature: відповіді на прогалини аналізу через реальні use cases.

Аналіз, вакансії й факти — справжні `AnalysisUseCases`, `JobUseCases`, `FactUseCases` з in-memory
адаптерами через портал. Прогалини додаються в чернетку і зберігаються кроком «я аналізую
вакансію N»; номер факту — `fact_number`, лічильник на користувача.
"""

import functools
import re
from collections.abc import Callable
from datetime import timedelta
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
    GapAnswerInput,
    GapInput,
)
from application.contracts.facts import FactData, FactInput
from application.contracts.jobs import JobInput
from application.facts.use_cases import FactUseCases
from application.jobs.use_cases import JobUseCases
from application.ports.prompts import PromptKey
from domain.identity.ids import UserId
from domain.shared.errors import DomainError, InvalidValue
from tests.support.analysis import InMemoryAnalysisUnitOfWork
from tests.support.clock import FakeClock
from tests.support.facts import InMemoryFactUnitOfWork
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store

scenarios("features/gaps_answer.feature")

Step = Callable[..., Any]

PAIR = re.compile(r'(?P<kind>[^\s";]+) "(?P<text>[^"]*)"')
RUBRIC_TEMPLATE = (
    "Score for {candidate}. Domain fit with target domains{domain_examples}; "
    "gaps: what {candidate} lacks."
)


class FakePrompts:
    def get(self, key: PromptKey) -> str:
        return {PromptKey.ANALYSIS_RUBRIC: RUBRIC_TEMPLATE}[key]


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


def setup(pattern: str) -> Callable[[Step], Step]:
    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(step)
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


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
        self.facts_store = FactStore.empty()
        self.profiles: dict[Any, Any] = {}
        self.inputs_changed: dict[Any, Any] = {}
        self.jobs = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.jobs_store), clock, ids
        )
        self.facts = FactUseCases(
            lambda: InMemoryFactUnitOfWork(self.facts_store), clock, ids
        )
        self.analysis = AnalysisUseCases(
            lambda: InMemoryAnalysisUnitOfWork(
                self.jobs_store, self.facts_store, self.profiles, self.inputs_changed
            ),
            clock,
            ids,
            FakePrompts(),
        )
        self.actors: dict[str, Actor] = {}
        self.current = ""
        self.draft_gaps: list[GapInput] = []
        self.error: DomainError | None = None

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

    def analysis_of(self, number: int) -> AnalysisData:
        return self.portal.call(self.analysis.get_analysis, self.actor, number)

    def brief(self, number: int) -> AnalysisBriefData:
        return self.portal.call(self.analysis.prepare_analysis, self.actor, number)

    def library(self) -> list[FactData]:
        return list(self.portal.call(self.facts.list_facts, self.actor).facts)

    def fact(self, number: int) -> FactData:
        found = [f for f in self.library() if f.fact_number == number]
        assert found, f"факту {number} нема в бібліотеці"
        return found[0]

    def gap(self, place: int, number: int) -> Any:
        return self.analysis_of(number).gaps[place - 1]


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


@setup(r'^є вакансія "(?P<title>[^"]*)" з текстом "(?P<text>[^"]*)"$')
def job_with_text(world: World, title: str, text: str) -> None:
    data = JobInput(text=text, title=title, company="Acme")
    world.attempt(lambda: world.jobs.add_job(world.actor, data))
    assert world.error is None, world.error


@setup(
    r'^у чернетці аналізу прогалина "(?P<gap>[^"]*)" з питанням "(?P<question>[^"]*)"$'
)
def draft_gap(world: World, gap: str, question: str) -> None:
    world.draft_gaps.append(GapInput(gap=gap, question=question))


@action(r"^я (?:аналізую|проаналізував) вакансію (?P<number>\d+)$")
def analyse(world: World, number: str) -> None:
    gaps, world.draft_gaps = world.draft_gaps, []
    data = AnalysisInput(score=70, summary="Підсумок.", gaps=gaps)
    world.attempt(lambda: world.analysis.save_analysis(world.actor, int(number), data))


@action(r'^я (?:додаю|додав) факт (?P<kind>[^\s"]+) "(?P<text>[^"]*)"$')
def add_fact(world: World, kind: str, text: str) -> None:
    world.attempt(
        lambda: world.facts.save_facts(world.actor, [FactInput(kind=kind, text=text)])
    )


# --- відповідь на прогалину ------------------------------------------------------------------


@action(
    r'^я (?:відповідаю|відповів) "(?P<answer>так|ні)" на прогалину (?P<gap>\d+)'
    r"(?: вакансії (?P<job>\d+))?(?: з фактами (?P<facts>.+))?$"
)
def answer_gap(
    world: World, answer: str, gap: str, job: str | None, facts: str | None
) -> None:
    pairs = PAIR.findall(facts or "")
    data = GapAnswerInput(
        has_experience=answer == "так",
        facts=[FactInput(kind=kind, text=text) for kind, text in pairs],
    )
    world.attempt(
        lambda: world.analysis.answer_gap(world.actor, int(job or 1), int(gap), data)
    )


@bdd_then("відповідь збережено без помилки")
def answer_saved(world: World) -> None:
    assert world.error is None, world.error


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)"$'))
def error_code(world: World, code: str) -> None:
    assert world.error is not None, "помилки не було"
    assert world.error.code == code


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" для поля "(?P<field>[^"]*)"$'))
def error_field(world: World, code: str, field: str) -> None:
    error = world.error
    assert isinstance(error, InvalidValue), error
    assert (error.code, error.field) == (code, field)


# --- факти -----------------------------------------------------------------------------------


@bdd_then(
    rx(r'^факт (?P<number>\d+) має вид "(?P<kind>[^"]*)" і текст "(?P<text>[^"]*)"$')
)
def fact_has(world: World, number: str, kind: str, text: str) -> None:
    fact = world.fact(int(number))
    assert (fact.kind.value, fact.text) == (kind, text)


@bdd_then(rx(r'^факт (?P<number>\d+) має джерело "(?P<source>[^"]*)"$'))
def fact_source(world: World, number: str, source: str) -> None:
    assert world.fact(int(number)).source.value == source


@bdd_then(rx(r"^факт (?P<number>\d+) підтверджений$"))
def fact_confirmed(world: World, number: str) -> None:
    assert world.fact(int(number)).confirmed is True


@bdd_given(rx(r"^факт (?P<number>\d+) не підтверджений$"))
@bdd_then(rx(r"^факт (?P<number>\d+) не підтверджений$"))
def fact_unconfirmed(world: World, number: str) -> None:
    assert world.fact(int(number)).confirmed is False


@bdd_then(rx(r"^факт (?P<number>\d+) прив'язаний до вакансії (?P<job>\d+)$"))
def fact_job(world: World, number: str, job: str) -> None:
    assert world.fact(int(number)).job_id == int(job)


@bdd_then(rx(r"^у бібліотеці (?P<count>\d+) (?:факт|факти|фактів)$"))
def library_size(world: World, count: str) -> None:
    assert len(world.library()) == int(count)


# --- прогалини й аналіз ----------------------------------------------------------------------


@bdd_then(
    rx(
        r'^прогалина (?P<place>\d+) аналізу вакансії (?P<job>\d+) закрита фактами "(?P<numbers>[^"]*)"$'
    )
)
def gap_closed(world: World, place: str, job: str, numbers: str) -> None:
    answer = world.gap(int(place), int(job)).answer
    assert answer is not None, "відповіді нема"
    assert answer.has_experience is True
    assert answer.fact_numbers == tuple(int(n) for n in numbers.split(";"))


@bdd_then(rx(r"^прогалина (?P<place>\d+) аналізу вакансії (?P<job>\d+) без досвіду$"))
def gap_no_experience(world: World, place: str, job: str) -> None:
    answer = world.gap(int(place), int(job)).answer
    assert answer is not None, "відповіді нема"
    assert (answer.has_experience, answer.fact_numbers) == (False, ())


@bdd_then(rx(r"^прогалина (?P<place>\d+) аналізу вакансії (?P<job>\d+) відкрита$"))
def gap_open(world: World, place: str, job: str) -> None:
    assert world.gap(int(place), int(job)).answer is None


@bdd_then(rx(r"^аналіз вакансії (?P<number>\d+) не застарілий$"))
def analysis_fresh(world: World, number: str) -> None:
    assert world.analysis_of(int(number)).stale_since is None


@bdd_then(rx(r'^аналіз вакансії (?P<number>\d+) застарів із "(?P<moment>[^"]*)"$'))
def analysis_stale(world: World, number: str, moment: str) -> None:
    stale = world.analysis_of(int(number)).stale_since
    assert stale is not None, "аналіз не застарілий"
    assert stale.isoformat() == moment


@bdd_then(
    rx(
        r'^у брифі аналізу вакансії (?P<job>\d+) одна відповідь на прогалину "(?P<gap>[^"]*)"$'
    )
)
def brief_single_answer(world: World, job: str, gap: str) -> None:
    answers = world.brief(int(job)).gap_answers
    assert [item.gap for item in answers] == [gap]


@bdd_then(
    rx(
        r'^у брифі аналізу вакансії (?P<job>\d+) відповідь на прогалину "(?P<gap>[^"]*)": без досвіду, фактів (?P<count>\d+)$'
    )
)
def brief_no_experience(world: World, job: str, gap: str, count: str) -> None:
    (found,) = [item for item in world.brief(int(job)).gap_answers if item.gap == gap]
    assert (found.has_experience, len(found.fact_numbers)) == (False, int(count))
