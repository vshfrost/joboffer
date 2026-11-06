"""Кроки для features/sources_manage.feature: керування джерелами через use case й in-memory адаптери,
без мережі й бази.

Джерела й стани прогону «у мене» / «у "Наталя"» задаються напряму в сховищі; додавання, вимкнення й
видалення — справжні виклики use case. Пробний запит слагу — `FakeProbe`. Вакансії для «лишаються»
з'являються справжнім прогоном `SourceRunUseCases` на тому самому сховищі. Помилки use case не падають
крок, а лягають у `world.error` — їх перевіряють кроки «отримую помилку …»."""

import functools
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.jobs import JobSearchInput
from application.contracts.sources import CompanyInput, FeedInput
from application.jobs.use_cases import JobUseCases
from application.sources.manage import SourceManageUseCases
from application.sources.refresh import SourceRunUseCases
from domain.identity.ids import UserId
from domain.shared.errors import DomainError, InvalidValue
from domain.sources.failure import FailureReason
from domain.sources.ids import SourceId
from domain.sources.importing import ImportSummary
from domain.sources.kinds import FeedSource, Platform, SourceKind
from domain.sources.manage import CompanyRow, FeedRow, SourceList
from domain.sources.posting import Posting
from domain.sources.run import SourceRun, Subscription
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork
from tests.support.source_manage import FakeProbe, InMemorySourceManageUnitOfWork
from tests.support.source_runs import (
    InMemorySourceRunUnitOfWork,
    SourceRunStore,
    registry,
)

scenarios("features/sources_manage.feature")

Step = Callable[..., Any]
KINDS: dict[str, SourceKind] = {
    "Greenhouse": Platform.GREENHOUSE,
    "Ashby": Platform.ASHBY,
    "Lever": Platform.LEVER,
    "DOU": FeedSource.DOU,
    "Djinni": FeedSource.DJINNI,
}
PLATFORMS = {name: kind for name, kind in KINDS.items() if isinstance(kind, Platform)}
FEEDS = {name: kind for name, kind in KINDS.items() if isinstance(kind, FeedSource)}
PLATFORM = r"(?P<kind>Greenhouse|Ashby|Lever)"
FEED = r"(?P<kind>DOU|Djinni)"
SOURCE = r'(?P<kind>Greenhouse|Ashby|Lever|DOU|Djinni) "(?P<ref>[^"]*)"'
OWNER = r'(?: користувача "(?P<owner>[^"]*)")?'
SUMMARY = (
    r": знайдено (?P<found>\d+), імпортовано (?P<imported>\d+), відкинуто (?P<filtered>\d+),"
    r" дублів (?P<duplicate>\d+), доповнено (?P<completed>\d+)"
)
LONG_NAME = "N" * 201


def rx(pattern: str) -> Any:
    return parsers.re(pattern)


def listed(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split(";") if part.strip())


def summary_of(
    found: str, imported: str, filtered: str, duplicate: str, completed: str
) -> ImportSummary:
    return ImportSummary(
        found=int(found),
        imported=int(imported),
        filtered=int(filtered),
        duplicate=int(duplicate),
        completed=int(completed),
    )


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.store = SourceRunStore()
        self.probe = FakeProbe()
        self.reads: list[Any] = []
        self.scripts = registry(KINDS.values(), self.reads)
        self.manage = SourceManageUseCases(
            lambda: InMemorySourceManageUnitOfWork(self.store), self.probe, ids
        )
        self.runs = SourceRunUseCases(
            lambda: InMemorySourceRunUnitOfWork(self.store),
            self.scripts,
            clock,
            ids,
        )
        self.jobs = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.store.jobs), clock, ids
        )
        self.actors: dict[str, Actor] = {}
        self.me = ""
        # (користувач, вид, ref) → id джерела, відомий сценарію (і після видалення).
        self.known: dict[tuple[str, SourceKind, str], SourceId] = {}
        self.error: DomainError | None = None
        self.result: CompanyRow | FeedRow | None = None
        self.posted = 0

    def actor(self, name: str | None = None) -> Actor:
        return self.actors[name or self.me]

    def attempt(self, call: Callable[..., Awaitable[Any]], *args: Any) -> None:
        """Виконує дію користувача; помилка домену лягає в `error`."""
        self.error, self.result = None, None
        try:
            self.result = self.portal.call(call, self.actor(), *args)
        except DomainError as exc:
            self.error = exc

    def listing(self) -> SourceList:
        return self.portal.call(self.manage.list_sources, self.actor())

    def seed(
        self, user: str, kind: str, ref: str, name: str, *, enabled: bool
    ) -> Subscription:
        sub = Subscription(
            id=SourceId(self.ids.new()),
            user_id=self.actor(user).user_id,
            kind=KINDS[kind],
            ref=ref,
            name=name,
        )
        self.store.subscriptions[sub.id] = (sub, enabled)
        self.known[(user, sub.kind, ref)] = sub.id
        return sub

    def source_id(self, user: str | None, kind: str, ref: str) -> str:
        return str(self.known[(user or self.me, KINDS[kind], ref)])

    def company(self, kind: str, ref: str) -> CompanyRow:
        found = [
            row
            for row in self.listing().companies
            if (row.company.platform, row.company.slug) == (KINDS[kind], ref)
        ]
        assert len(found) == 1, f"у списку {kind} «{ref}»: {len(found)}"
        return found[0]

    def feed(self, kind: str, ref: str) -> FeedRow:
        found = [
            row
            for row in self.listing().feeds
            if (row.feed.source, row.feed.query) == (KINDS[kind], ref)
        ]
        assert len(found) == 1, f"у списку {kind} «{ref}»: {len(found)}"
        return found[0]

    def run_of(self, kind: str, ref: str) -> SourceRun | None:
        row = self.company(kind, ref) if kind in PLATFORMS else self.feed(kind, ref)
        return row.run

    def my_jobs(self, source: str) -> list[Any]:
        return self.portal.call(
            self.jobs.list_jobs, self.actor(), JobSearchInput(source=source, limit=200)
        )


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def succeeded(step: Step) -> Step:
    """Крок-передумова: дія має вдатися, інакше сценарій не про те."""

    @functools.wraps(step)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        step(*args, **kwargs)
        world: World = kwargs["world"]
        assert world.error is None, world.error

    return wrapper


def action(pattern: str) -> Callable[[Step], Step]:
    """Один текст — і «Припустимо я …», і «Якщо я …»."""

    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(succeeded(step))
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


# --- користувачі, джерела, прогони ----------------------------------------------------------


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
def i_am(world: World, user: str) -> None:
    world.me = user


OWN = r'(?:у мене|у "(?P<user>[^"]*)")'


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


@bdd_given(rx(rf'^{OWN} є (?P<off>вимкнена )?стрічка {FEED} "(?P<ref>[^"]*)"$'))
def has_feed(
    world: World, user: str | None, off: str | None, kind: str, ref: str
) -> None:
    world.seed(user or world.me, kind, ref, "", enabled=off is None)


@bdd_given(rx(rf"^останній прогін {SOURCE}{SUMMARY}$"))
def last_run(
    world: World,
    kind: str,
    ref: str,
    found: str,
    imported: str,
    filtered: str,
    duplicate: str,
    completed: str,
) -> None:
    sub_id = world.known[(world.me, KINDS[kind], ref)]
    summary = summary_of(found, imported, filtered, duplicate, completed)
    world.store.runs[sub_id] = SourceRun(world.clock.now(), summary, error=None)


@bdd_given(rx(rf'^останній прогін {SOURCE} закінчився помилкою "(?P<code>[^"]*)"$'))
def last_run_failed(world: World, kind: str, ref: str, code: str) -> None:
    sub_id = world.known[(world.me, KINDS[kind], ref)]
    world.store.runs[sub_id] = SourceRun(
        world.clock.now(), ImportSummary(), FailureReason(code)
    )


@bdd_given(
    rx(rf'^пробний запит для {PLATFORM} "(?P<ref>[^"]*)" не знаходить компанії$')
)
def probe_not_found(world: World, kind: str, ref: str) -> None:
    world.probe.failures[(PLATFORMS[kind], ref)] = FailureReason.NOT_FOUND


@bdd_given(
    rx(
        rf'^пробний запит для {PLATFORM} "(?P<ref>[^"]*)" не вдається з помилкою "(?P<code>[^"]*)"$'
    )
)
def probe_fails(world: World, kind: str, ref: str, code: str) -> None:
    world.probe.failures[(PLATFORMS[kind], ref)] = FailureReason(code)


@bdd_given(
    rx(
        rf'^під час пробного запиту для {PLATFORM} "(?P<ref>[^"]*)" ту саму компанію додає хтось інший$'
    )
)
def probe_race(world: World, kind: str, ref: str) -> None:
    def meanwhile() -> None:
        world.seed(world.me, kind, ref, "Acme", enabled=True)

    world.probe.during[(PLATFORMS[kind], ref)] = meanwhile


@bdd_given(rx(rf'^(?:компанія|стрічка) {SOURCE} віддає вакансії "(?P<titles>[^"]*)"$'))
def source_offers(world: World, kind: str, ref: str, titles: str) -> None:
    postings = []
    for title in listed(titles):
        world.posted += 1
        postings.append(
            Posting(
                title=title,
                url=f"https://jobs.example/{world.posted}",
                text=f"Опис вакансії «{title}»",
                company="Globex" if kind in FEEDS else None,
            )
        )
    world.scripts[KINDS[kind]].postings[ref] = postings


@bdd_given(rx(r"^відбувається прогін джерел$"))
def run_refresh(world: World) -> None:
    world.clock.advance(timedelta(minutes=1))
    world.portal.call(world.runs.refresh_sources)


# --- дії ------------------------------------------------------------------------------------


@bdd_when(rx(r"^я переглядаю свої джерела$"))
def view_sources(world: World) -> None:
    world.listing()


@bdd_when(
    rx(
        r'^я додаю компанію з платформою "(?P<platform>[^"]*)", слагом "(?P<slug>[^"]*)" і назвою "(?P<name>[^"]*)"$'
    )
)
def add_company(world: World, platform: str, slug: str, name: str) -> None:
    world.attempt(world.manage.add_company, CompanyInput(platform, slug, name))


@bdd_when(
    rx(
        r'^я додаю компанію з платформою "(?P<platform>[^"]*)", слагом "(?P<slug>[^"]*)" і дуже довгою назвою$'
    )
)
def add_company_long_name(world: World, platform: str, slug: str) -> None:
    world.attempt(world.manage.add_company, CompanyInput(platform, slug, LONG_NAME))


@bdd_when(
    rx(r'^я додаю стрічку з джерелом "(?P<source>[^"]*)" і запитом "(?P<query>[^"]*)"$')
)
def add_feed(world: World, source: str, query: str) -> None:
    world.attempt(world.manage.add_feed, FeedInput(source, query))


@action(rf"^я (?P<verb>вимикаю|вмикаю) компанію {SOURCE}{OWNER}$")
def toggle_company(
    world: World, verb: str, kind: str, ref: str, owner: str | None
) -> None:
    world.attempt(
        world.manage.set_company_enabled,
        world.source_id(owner, kind, ref),
        verb == "вмикаю",
    )


@action(rf"^я (?P<verb>вимикаю|вмикаю) стрічку {SOURCE}{OWNER}$")
def toggle_feed(
    world: World, verb: str, kind: str, ref: str, owner: str | None
) -> None:
    world.attempt(
        world.manage.set_feed_enabled,
        world.source_id(owner, kind, ref),
        verb == "вмикаю",
    )


@action(rf"^я видаляю компанію {SOURCE}{OWNER}$")
def remove_company(world: World, kind: str, ref: str, owner: str | None) -> None:
    world.attempt(world.manage.remove_company, world.source_id(owner, kind, ref))


@action(rf"^я видаляю стрічку {SOURCE}{OWNER}$")
def remove_feed(world: World, kind: str, ref: str, owner: str | None) -> None:
    world.attempt(world.manage.remove_feed, world.source_id(owner, kind, ref))


@bdd_when(rx(rf"^я вимикаю стрічку за id компанії {SOURCE}$"))
def toggle_feed_by_company_id(world: World, kind: str, ref: str) -> None:
    world.attempt(
        world.manage.set_feed_enabled, world.source_id(None, kind, ref), False
    )


@bdd_when(rx(rf"^я видаляю компанію за id стрічки {SOURCE}$"))
def remove_company_by_feed_id(world: World, kind: str, ref: str) -> None:
    world.attempt(world.manage.remove_company, world.source_id(None, kind, ref))


@bdd_when(
    rx(
        r'^я (?P<verb>вимикаю|видаляю) (?P<what>компанію|стрічку) з id "(?P<raw>[^"]*)"$'
    )
)
def act_on_raw_id(world: World, verb: str, what: str, raw: str) -> None:
    calls = {
        ("вимикаю", "компанію"): lambda: world.attempt(
            world.manage.set_company_enabled, raw, False
        ),
        ("вимикаю", "стрічку"): lambda: world.attempt(
            world.manage.set_feed_enabled, raw, False
        ),
        ("видаляю", "компанію"): lambda: world.attempt(
            world.manage.remove_company, raw
        ),
        ("видаляю", "стрічку"): lambda: world.attempt(world.manage.remove_feed, raw),
    }
    calls[(verb, what)]()


# --- результат ------------------------------------------------------------------------------


@bdd_then(
    rx(
        r"^у списку (?P<companies>\d+) (?:компанія|компанії|компаній)"
        r" і (?P<feeds>\d+) (?:стрічка|стрічки|стрічок)$"
    )
)
def list_counts(world: World, companies: str, feeds: str) -> None:
    listing = world.listing()
    assert (len(listing.companies), len(listing.feeds)) == (
        int(companies),
        int(feeds),
    )


@bdd_then(
    rx(
        rf'^у списку є компанія {PLATFORM} "(?P<ref>[^"]*)" з назвою "(?P<name>[^"]*)",'
        r" (?P<state>увімкнена|вимкнена)$"
    )
)
def company_listed(world: World, kind: str, ref: str, name: str, state: str) -> None:
    company = world.company(kind, ref).company
    assert (company.name, company.enabled) == (name, state == "увімкнена")


@bdd_then(
    rx(rf'^у списку є стрічка {FEED} "(?P<ref>[^"]*)", (?P<state>увімкнена|вимкнена)$')
)
def feed_listed(world: World, kind: str, ref: str, state: str) -> None:
    assert world.feed(kind, ref).feed.enabled == (state == "увімкнена")


@bdd_then(rx(rf"^{SOURCE} у списку без прогону$"))
def listed_without_run(world: World, kind: str, ref: str) -> None:
    assert world.run_of(kind, ref) is None


@bdd_then(rx(rf"^{SOURCE} у списку з прогоном{SUMMARY}$"))
def listed_run_summary(
    world: World,
    kind: str,
    ref: str,
    found: str,
    imported: str,
    filtered: str,
    duplicate: str,
    completed: str,
) -> None:
    run = world.run_of(kind, ref)
    assert run is not None
    assert run.summary == summary_of(found, imported, filtered, duplicate, completed)


@bdd_then(rx(rf"^{SOURCE} у списку з прогоном без помилки$"))
def listed_run_ok(world: World, kind: str, ref: str) -> None:
    run = world.run_of(kind, ref)
    assert run is not None
    assert run.error is None


@bdd_then(rx(rf'^{SOURCE} у списку з прогоном і помилкою "(?P<code>[^"]*)"$'))
def listed_run_error(world: World, kind: str, ref: str, code: str) -> None:
    run = world.run_of(kind, ref)
    assert run is not None
    assert run.error == FailureReason(code)


@bdd_then(rx(r"^(?:компанію|стрічку) додано$"))
def added(world: World) -> None:
    assert world.error is None, world.error
    assert world.result is not None


@bdd_then(rx(r"^видалення пройшло$"))
def removed(world: World) -> None:
    assert world.error is None, world.error


@bdd_then(
    rx(
        r"^відповідь: компанія "
        rf'{PLATFORM} "(?P<ref>[^"]*)" (?P<state>увімкнена|вимкнена), прогін{SUMMARY}$'
    )
)
def toggled_answer(
    world: World,
    kind: str,
    ref: str,
    state: str,
    found: str,
    imported: str,
    filtered: str,
    duplicate: str,
    completed: str,
) -> None:
    assert world.error is None, world.error
    assert isinstance(world.result, CompanyRow)
    assert (world.result.company.platform, world.result.company.slug) == (
        PLATFORMS[kind],
        ref,
    )
    assert world.result.company.enabled == (state == "увімкнена")
    assert world.result.run is not None
    summary = summary_of(found, imported, filtered, duplicate, completed)
    assert world.result.run.summary == summary


@bdd_then(
    rx(
        r'^пробних запитів було (?P<count>\d+): (?P<kind>Greenhouse|Ashby|Lever) "(?P<ref>[^"]*)"$'
    )
)
def probed(world: World, count: str, kind: str, ref: str) -> None:
    assert world.probe.checked == [(PLATFORMS[kind], ref)] * int(count)


@bdd_then(rx(r"^пробних запитів не було$"))
def not_probed(world: World) -> None:
    assert world.probe.checked == []


@bdd_then(
    rx(
        r'^отримую помилку "(?P<code>[^"]*)"'
        r'(?: біля поля "(?P<field>[^"]*)")?'
        r'(?: з текстом(?P<part>, що містить)? "(?P<text>[^"]*)")?$'
    )
)
def got_error(
    world: World, code: str, field: str | None, part: str | None, text: str | None
) -> None:
    error = world.error
    assert error is not None, "помилки не було"
    assert error.code == code
    if field is not None:
        assert isinstance(error, InvalidValue)
        assert error.field == field
    if text is not None:
        assert (text in error.message) if part else (error.message == text)


@bdd_then(
    rx(rf'^компанія {SOURCE} користувача "(?P<owner>[^"]*)" лишилась увімкненою$')
)
def others_company_intact(world: World, kind: str, ref: str, owner: str) -> None:
    sub, enabled = world.store.subscriptions[world.known[(owner, KINDS[kind], ref)]]
    assert enabled
    assert sub.user_id == world.actor(owner).user_id


@bdd_then(rx(rf'^стрічка {SOURCE} користувача "(?P<owner>[^"]*)" лишилась увімкненою$'))
def others_feed_intact(world: World, kind: str, ref: str, owner: str) -> None:
    _, enabled = world.store.subscriptions[world.known[(owner, KINDS[kind], ref)]]
    assert enabled


@bdd_then(rx(rf"^стану прогону {SOURCE} нема$"))
def run_state_gone(world: World, kind: str, ref: str) -> None:
    assert world.known[(world.me, KINDS[kind], ref)] not in world.store.runs


@bdd_then(
    rx(
        r'^я маю (?P<count>\d+) (?:вакансію|вакансії|вакансій) з джерелом "(?P<source>[^"]*)"$'
    )
)
def job_count(world: World, count: str, source: str) -> None:
    assert len(world.my_jobs(source)) == int(count)
