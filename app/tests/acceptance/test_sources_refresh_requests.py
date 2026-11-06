"""Кроки для features/sources_refresh_requests.feature: «Оновити зараз» — ліміт запитів на користувача,
рядки в черзі, які позначає прогін, і стан у списку джерел. Use cases й in-memory адаптери, без мережі й бази.

Джерела «у мене» / «у "Наталя"» задаються напряму в сховищі; прогін — справжній `SourceRunUseCases` на тому ж
сховищі (адаптери-сценарії віддають порожні списки). Час стоїть на 2026-01-01 09:00 UTC (10:00 у Мадриді),
доки сценарій його не посуне. Помилки use case лягають у `world.error`, а не валять крок."""

import functools
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.sources import RefreshState
from application.sources.overview import SourceOverviewUseCases
from application.sources.refresh import SourceRunUseCases
from domain.identity.ids import UserId
from domain.shared.errors import DomainError
from domain.shared.local_time import local_time
from domain.sources.ids import SourceId
from domain.sources.kinds import FeedSource, Platform, SourceKind
from domain.sources.refresh_requests import MANUAL_REFRESH_LIMIT, RefreshLimit
from domain.sources.run import Subscription
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.source_overview import InMemorySourceOverviewUnitOfWork
from tests.support.source_runs import (
    InMemorySourceRunUnitOfWork,
    SourceRunStore,
    registry,
)

scenarios("features/sources_refresh_requests.feature")

Step = Callable[..., Any]
KINDS: dict[str, SourceKind] = {
    "Greenhouse": Platform.GREENHOUSE,
    "Ashby": Platform.ASHBY,
    "Lever": Platform.LEVER,
    "DOU": FeedSource.DOU,
    "Djinni": FeedSource.DJINNI,
}
PLATFORM = r"(?P<kind>Greenhouse|Ashby|Lever)"
FEED = r"(?P<kind>DOU|Djinni)"
SOURCE = r'(?P<kind>Greenhouse|Ashby|Lever|DOU|Djinni) "(?P<ref>[^"]*)"'
OWN = r'(?:у мене|у "(?P<user>[^"]*)")'
ASK = r"(?:запитую|запитав|запитала)"


def rx(pattern: str) -> Any:
    return parsers.re(pattern)


def madrid(moment: Any) -> str:
    return f"{local_time(moment):%H:%M}"


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.store = SourceRunStore()
        self.overview = SourceOverviewUseCases(
            lambda: InMemorySourceOverviewUnitOfWork(self.store), clock
        )
        self.runs = SourceRunUseCases(
            lambda: InMemorySourceRunUnitOfWork(self.store),
            registry(KINDS.values(), []),
            clock,
            ids,
        )
        self.actors: dict[str, Actor] = {}
        self.me = ""
        self.known: dict[tuple[str, SourceKind, str], SourceId] = {}
        self.error: DomainError | None = None
        self.state: RefreshState | None = None

    def actor(self, name: str | None = None) -> Actor:
        return self.actors[name or self.me]

    def refresh_state(self) -> RefreshState:
        return self.portal.call(self.overview.overview, self.actor()).refresh

    def seed(self, user: str, kind: str, ref: str, name: str, *, enabled: bool) -> None:
        sub = Subscription(
            id=SourceId(self.ids.new()),
            user_id=self.actor(user).user_id,
            kind=KINDS[kind],
            ref=ref,
            name=name,
        )
        self.store.subscriptions[sub.id] = (sub, enabled)
        self.known[(user, sub.kind, ref)] = sub.id

    def requests(self, *, handled: bool) -> int:
        return sum(
            1
            for _, _, done in self.store.refresh_requests
            if (done is not None) == handled
        )


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def action(pattern: str) -> Callable[[Step], Step]:
    """Один текст — і «Припустимо я …», і «Якщо я …»; у передумові дія має вдатися."""

    def decorate(step: Step) -> Step:
        @functools.wraps(step)
        def checked(*args: Any, **kwargs: Any) -> None:
            step(*args, **kwargs)
            world: World = kwargs["world"]
            assert world.error is None, world.error

        bdd_given(rx(pattern), stacklevel=2)(checked)
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


# --- користувачі, джерела, час ----------------------------------------------------------------


@bdd_given(rx(r'^є користувачі "(?P<first>[^"]*)" та "(?P<second>[^"]*)"$'))
def users(world: World, first: str, second: str) -> None:
    for name in (first, second):
        world.actors[name] = Actor(
            user_id=UserId(world.ids.new()),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )


@bdd_given(rx(r'^я — користувач "(?P<user>[^"]*)"$'))
@bdd_given(rx(r'^я стаю користувачем "(?P<user>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<user>[^"]*)"$'))
def i_am(world: World, user: str) -> None:
    world.me = user
    world.error, world.state = None, None


@bdd_given(
    rx(
        rf'^{OWN} є (?P<off>вимкнена )?компанія {PLATFORM} "(?P<ref>[^"]*)" з назвою "(?P<name>[^"]*)"$'
    )
)
def has_company(
    world: World,
    user: str | None,
    off: str | None,
    kind: str,
    ref: str,
    name: str,
) -> None:
    world.seed(user or world.me, kind, ref, name, enabled=off is None)


@bdd_given(rx(rf'^{OWN} є стрічка {FEED} "(?P<ref>[^"]*)"$'))
def has_feed(world: World, user: str | None, kind: str, ref: str) -> None:
    world.seed(user or world.me, kind, ref, "", enabled=True)


@bdd_given(rx(rf"^(?:компанія|стрічка) {SOURCE} вимкнена$"))
def source_disabled(world: World, kind: str, ref: str) -> None:
    sub_id = world.known[(world.me, KINDS[kind], ref)]
    sub, _ = world.store.subscriptions[sub_id]
    world.store.subscriptions[sub_id] = (sub, False)


@bdd_given(rx(r"^минає (?P<minutes>\d+) хв\.$"))
@bdd_when(rx(r"^минає (?P<minutes>\d+) хв\.$"))
def time_passes(world: World, minutes: str) -> None:
    world.clock.advance(timedelta(minutes=int(minutes)))


@bdd_given(rx(r"^відбувається прогін джерел$"))
@bdd_when(rx(r"^відбувається прогін джерел$"))
def run_refresh(world: World) -> None:
    world.portal.call(world.runs.refresh_sources)


# --- дії --------------------------------------------------------------------------------------


@action(rf"^я {ASK} оновлення джерел$")
def request_refresh(world: World) -> None:
    world.error, world.state = None, None
    try:
        world.state = world.portal.call(world.overview.request_refresh, world.actor())
    except DomainError as exc:
        world.error = exc


@bdd_when(rx(r"^я переглядаю свої джерела$"))
def view_sources(world: World) -> None:
    world.refresh_state()


# --- результат --------------------------------------------------------------------------------


@bdd_then(rx(r"^(?P<count>\d+) запит\w* оновлення чека\w+ на виконання$"))
def requests_pending(world: World, count: str) -> None:
    assert world.requests(handled=False) == int(count)


@bdd_then(rx(r"^(?P<count>\d+) запит\w* оновлення позначено виконан\w+$"))
def requests_handled(world: World, count: str) -> None:
    assert world.requests(handled=True) == int(count)


@bdd_then(rx(r"^ліміт запитів оновлення — (?P<limit>\d+), лишилось (?P<left>\d+)$"))
def overview_limit(world: World, limit: str, left: str) -> None:
    assert int(limit) == MANUAL_REFRESH_LIMIT
    assert world.refresh_state().remaining == int(left)


@bdd_then(rx(r"^наступного запиту чекати не треба$"))
def no_wait(world: World) -> None:
    assert world.refresh_state().next_at is None


@bdd_then(
    rx(
        r"^відповідь на запит: лишилось (?P<left>\d+), наступного запиту чекати не треба$"
    )
)
def answer_no_wait(world: World, left: str) -> None:
    assert world.error is None, world.error
    assert world.state is not None
    assert (world.state.remaining, world.state.next_at) == (int(left), None)


@bdd_then(
    rx(
        r'^відповідь на запит: лишилось (?P<left>\d+), наступний запит о "(?P<time>\d\d:\d\d)" за Мадридом$'
    )
)
def answer_wait(world: World, left: str, time: str) -> None:
    assert world.error is None, world.error
    assert world.state is not None
    assert world.state.remaining == int(left)
    assert world.state.next_at is not None
    assert madrid(world.state.next_at) == time


@bdd_then(
    rx(r'^відповідь на запит: останнє оновлення "(?P<time>\d\d:\d\d)" за Мадридом$')
)
def answer_last_run(world: World, time: str) -> None:
    assert world.state is not None
    assert world.state.last_run_at is not None
    assert madrid(world.state.last_run_at) == time


@bdd_then(
    rx(
        r'^у списку джерел лишилось (?P<left>\d+) запит\w*, наступний о "(?P<time>\d\d:\d\d)" за Мадридом$'
    )
)
def overview_wait(world: World, left: str, time: str) -> None:
    state = world.refresh_state()
    assert state.remaining == int(left)
    assert state.next_at is not None
    assert madrid(state.next_at) == time


@bdd_then(
    rx(r'^запит оновлення відхилено: час повтору — "(?P<time>\d\d:\d\d)" за Мадридом$')
)
def refresh_limit_time(world: World, time: str) -> None:
    assert isinstance(world.error, RefreshLimit), world.error
    assert madrid(world.error.next_at) == time
    assert f"наступне о {time} (Мадрид)" in world.error.message


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)"$'))
def got_error(world: World, code: str) -> None:
    assert world.error is not None, "помилки не було"
    assert world.error.code == code


@bdd_then(rx(r"^останнє оновлення джерел: ще не було$"))
def never_refreshed(world: World) -> None:
    assert world.refresh_state().last_run_at is None


@bdd_then(rx(r'^останнє оновлення джерел: "(?P<time>\d\d:\d\d)" за Мадридом$'))
def refreshed_at(world: World, time: str) -> None:
    last = world.refresh_state().last_run_at
    assert last is not None
    assert madrid(last) == time
