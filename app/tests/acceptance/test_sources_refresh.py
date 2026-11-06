"""Кроки для features/sources_refresh.feature: прогін усіх увімкнених джерел усіх користувачів через
use case й in-memory адаптери, без мережі й бази.

Джерела користувачів (компанії й стрічки) задаються кроками «у "<користувач>" є компанія …» — таблиці
керування з'являться в K45. Адаптер кожного виду — сценарій: що віддавати цілі чи яким кодом збоїти;
«для … адаптера нема» прибирає вид з реєстру. Стан прогону читається зі сховища, вакансії — через
use case вакансій."""

from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.jobs import JobData, JobSearchInput
from application.jobs.use_cases import JobUseCases
from application.sources.refresh import SourceRunUseCases
from domain.identity.ids import UserId
from domain.profile.profile import Profile
from domain.sources.failure import FailureReason
from domain.sources.ids import SourceId
from domain.sources.importing import ImportSummary
from domain.sources.kinds import FeedSource, Platform, SourceKind
from domain.sources.posting import Posting
from domain.sources.run import RefreshReport, SourceRun, Subscription
from domain.sources.target import SourceTarget
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork
from tests.support.source_runs import (
    InMemorySourceRunUnitOfWork,
    ScriptedSource,
    SourceRunStore,
    registry,
)

scenarios("features/sources_refresh.feature")

Step = Callable[..., Any]
KINDS: dict[str, SourceKind] = {
    "Greenhouse": Platform.GREENHOUSE,
    "Ashby": Platform.ASHBY,
    "Lever": Platform.LEVER,
    "DOU": FeedSource.DOU,
    "Djinni": FeedSource.DJINNI,
}
SOURCE = r'(?P<kind>Greenhouse|Ashby|Lever|DOU|Djinni) "(?P<ref>[^"]*)"'
USER = r'"(?P<user>[^"]*)"'
SUMMARY = (
    r": знайдено (?P<found>\d+), імпортовано (?P<imported>\d+), відкинуто (?P<filtered>\d+),"
    r" дублів (?P<duplicate>\d+), доповнено (?P<completed>\d+)"
)


def rx(pattern: str) -> Any:
    return parsers.re(pattern)


def listed(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split(";") if part.strip())


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.store = SourceRunStore()
        self.reads: list[SourceTarget] = []
        self.scripts = registry(KINDS.values(), self.reads)
        self.without_adapter: set[SourceKind] = set()
        self.actors: dict[str, Actor] = {}
        self.posted = 0
        self.report: RefreshReport | None = None
        self.aborted: Exception | None = None
        self.nested: RefreshReport | None = None
        # Джерела, видалені посеред прогону: (користувач, вид, ref) → підписка.
        self.removed: dict[tuple[str, SourceKind, str], Subscription] = {}
        # target.ref → (є стан «alpha», вакансій) на момент читання.
        self.seen: dict[str, tuple[bool, int]] = {}
        self.jobs = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.store.jobs), clock, ids
        )

    def user(self, name: str) -> Actor:
        return self.actors[name]

    def use_cases(self) -> SourceRunUseCases:
        sources = {
            kind: script
            for kind, script in self.scripts.items()
            if kind not in self.without_adapter
        }
        return SourceRunUseCases(
            lambda: InMemorySourceRunUnitOfWork(self.store),
            sources,
            self.clock,
            self.ids,
        )

    def subscribe(
        self, user: str, kind: str, ref: str, name: str, enabled: bool
    ) -> Subscription:
        sub = Subscription(
            id=SourceId(self.ids.new()),
            user_id=self.user(user).user_id,
            kind=KINDS[kind],
            ref=ref,
            name=name,
        )
        self.store.subscriptions[sub.id] = (sub, enabled)
        return sub

    def find(self, user: str, kind: str, ref: str) -> Subscription:
        for sub, _ in self.store.subscriptions.values():
            if (sub.user_id, sub.kind, sub.ref) == (
                self.user(user).user_id,
                KINDS[kind],
                ref,
            ):
                return sub
        raise AssertionError(f"у «{user}» нема джерела {kind} «{ref}»")

    def offer(self, kind: str, ref: str, titles: tuple[str, ...]) -> None:
        script = self.scripts[KINDS[kind]]
        postings = []
        for title in titles:
            self.posted += 1
            postings.append(
                Posting(
                    title=title,
                    url=f"https://jobs.example/{self.posted}",
                    text=f"Опис вакансії «{title}»",
                    company="Globex" if isinstance(KINDS[kind], FeedSource) else None,
                )
            )
        script.postings[ref] = postings
        script.failures.pop(ref, None)

    def refresh(self) -> None:
        """Прогін, що обірвався винятком, не валить крок: про це кажуть «прогін не обірвано»."""
        try:
            self.report = self.portal.call(self.use_cases().refresh_sources)
        except Exception as exc:
            self.aborted = exc

    def my_jobs(self, user: str, source: str = "") -> list[Any]:
        return self.portal.call(
            self.jobs.list_jobs,
            self.user(user),
            JobSearchInput(source=source, limit=200),
        )

    def job(self, user: str, title: str) -> JobData:
        found = [j for j in self.my_jobs(user) if j.title == title]
        assert len(found) == 1, f"вакансій «{title}» у «{user}»: {len(found)}"
        return self.portal.call(self.jobs.get_job, self.user(user), found[0].job_number)

    def state(self, user: str, kind: str, ref: str) -> SourceRun:
        sub = self.find(user, kind, ref)
        assert sub.id in self.store.runs, f"у «{user}» нема стану {kind} «{ref}»"
        return self.store.runs[sub.id]

    def reads_of(self, kind: str, ref: str) -> int:
        return sum(1 for t in self.reads if (t.kind, t.ref) == (KINDS[kind], ref))


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


# --- користувачі, профіль, час --------------------------------------------------------------


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


@bdd_given(rx(rf"^у профілі {USER} слова назви \"(?P<words>[^\"]*)\"$"))
def profile_keywords(world: World, user: str, words: str) -> None:
    uid = world.user(user).user_id
    profile = world.store.profiles.get(uid, Profile())
    rules = replace(profile.rules, title_keywords=listed(words))
    world.store.profiles[uid] = replace(profile, rules=rules)


@bdd_given(rx(r"^минає (?P<hours>\d+) годин$"))
def hours_pass(world: World, hours: str) -> None:
    world.clock.advance(timedelta(hours=int(hours)))


# --- джерела користувачів і адаптери --------------------------------------------------------


@bdd_given(
    rx(rf'^у {USER} є (?P<off>вимкнена )?компанія {SOURCE} з назвою "(?P<name>[^"]*)"$')
)
def has_company(
    world: World, user: str, off: str | None, kind: str, ref: str, name: str
) -> None:
    world.subscribe(user, kind, ref, name, enabled=off is None)


@bdd_given(rx(rf"^у {USER} є (?P<off>вимкнена )?стрічка {SOURCE}$"))
def has_feed(world: World, user: str, off: str | None, kind: str, ref: str) -> None:
    world.subscribe(user, kind, ref, "", enabled=off is None)


@bdd_given(rx(rf'^(?:компанія|стрічка) {SOURCE} віддає вакансії "(?P<titles>[^"]*)"$'))
def source_offers(world: World, kind: str, ref: str, titles: str) -> None:
    world.offer(kind, ref, listed(titles))


@bdd_given(
    rx(rf'^(?:компанія|стрічка) {SOURCE} не відповідає з помилкою "(?P<code>[^"]*)"$')
)
def source_fails(world: World, kind: str, ref: str, code: str) -> None:
    world.scripts[KINDS[kind]].failures[ref] = FailureReason(code)


@bdd_given(rx(r"^для (?P<kind>Greenhouse|Ashby|Lever|DOU|Djinni) адаптера нема$"))
def no_adapter(world: World, kind: str) -> None:
    world.without_adapter.add(KINDS[kind])


WATCHED = (
    r'(?P<watched_kind>Greenhouse|Ashby|Lever|DOU|Djinni) "(?P<watched_ref>[^"]*)"'
)


@bdd_given(rx(rf"^під час читання {SOURCE} я дивлюся на стан {WATCHED} у {USER}$"))
def watch_store(
    world: World,
    kind: str,
    ref: str,
    watched_kind: str,
    watched_ref: str,
    user: str,
) -> None:
    script: ScriptedSource = world.scripts[KINDS[kind]]
    watched = world.find(user, watched_kind, watched_ref)

    async def look() -> None:
        world.seen[ref] = (watched.id in world.store.runs, len(world.store.jobs.jobs))

    script.during[ref] = look


@bdd_given(rx(rf"^під час читання {SOURCE} стартує ще один прогін$"))
def nested_refresh(world: World, kind: str, ref: str) -> None:
    script: ScriptedSource = world.scripts[KINDS[kind]]

    async def again() -> None:
        world.nested = await world.use_cases().refresh_sources()

    script.during[ref] = again


@bdd_given(rx(rf"^(?:компанія|стрічка) {SOURCE} падає з несподіваною помилкою$"))
def source_crashes(world: World, kind: str, ref: str) -> None:
    world.scripts[KINDS[kind]].crashes[ref] = RuntimeError("розбір упав")


@bdd_given(rx(rf"^під час читання {SOURCE} {USER} видаляє джерело {WATCHED}$"))
def source_removed_mid_run(
    world: World,
    kind: str,
    ref: str,
    user: str,
    watched_kind: str,
    watched_ref: str,
) -> None:
    script: ScriptedSource = world.scripts[KINDS[kind]]
    doomed = world.find(user, watched_kind, watched_ref)

    async def remove() -> None:
        del world.store.subscriptions[doomed.id]
        world.removed[(user, doomed.kind, doomed.ref)] = doomed

    script.during[ref] = remove


# --- прогін ---------------------------------------------------------------------------------


@bdd_given(rx(r"^відбувається прогін джерел$"))
@bdd_when(rx(r"^відбувається прогін джерел$"))
def run_refresh(world: World) -> None:
    world.refresh()


# --- результат ------------------------------------------------------------------------------


@bdd_then(rx(r"^прогін прочитав (?P<count>\d+) (?:ціль|цілі|цілей)$"))
def targets_read(world: World, count: str) -> None:
    assert world.report is not None
    assert world.report.targets == int(count)


@bdd_then(rx(r"^прогін не обірвано$"))
def not_aborted(world: World) -> None:
    assert world.aborted is None, repr(world.aborted)
    assert world.report is not None


@bdd_then(rx(r"^прогін не заблоковано$"))
def not_locked(world: World) -> None:
    assert world.report is not None
    assert world.report.locked is False


@bdd_then(rx(r"^другий прогін пропущено як locked$"))
def nested_locked(world: World) -> None:
    assert world.nested is not None, "ще один прогін не стартував"
    assert world.nested.locked is True
    assert world.nested.runs == []


@bdd_then(rx(rf"^{SOURCE} не читалось$"))
def never_read(world: World, kind: str, ref: str) -> None:
    assert world.reads_of(kind, ref) == 0


@bdd_then(rx(rf"^{SOURCE} читалось (?P<count>\d+) (?:раз|рази)$"))
def read_times(world: World, kind: str, ref: str, count: str) -> None:
    assert world.reads_of(kind, ref) == int(count)


@bdd_then(
    rx(
        rf'^{USER} має (?P<count>\d+) (?:вакансію|вакансії|вакансій) з джерелом "(?P<source>[^"]*)"$'
    )
)
def job_count(world: World, user: str, count: str, source: str) -> None:
    assert len(world.my_jobs(user, source)) == int(count)


@bdd_then(
    rx(rf'^вакансія "(?P<title>[^"]*)" у {USER} має компанію "(?P<company>[^"]*)"$')
)
def job_company(world: World, title: str, user: str, company: str) -> None:
    assert world.job(user, title).company == company


@bdd_then(rx(rf"^стан {SOURCE} у {USER}{SUMMARY}$"))
def state_summary(
    world: World,
    kind: str,
    ref: str,
    user: str,
    found: str,
    imported: str,
    filtered: str,
    duplicate: str,
    completed: str,
) -> None:
    run = world.state(user, kind, ref)
    assert run.summary == ImportSummary(
        found=int(found),
        imported=int(imported),
        filtered=int(filtered),
        duplicate=int(duplicate),
        completed=int(completed),
    )


@bdd_then(rx(rf"^стан {SOURCE} у {USER} без помилки$"))
def state_ok(world: World, kind: str, ref: str, user: str) -> None:
    assert world.state(user, kind, ref).error is None


@bdd_then(rx(rf'^стан {SOURCE} у {USER} з помилкою "(?P<code>[^"]*)"$'))
def state_error(world: World, kind: str, ref: str, user: str, code: str) -> None:
    assert world.state(user, kind, ref).error == FailureReason(code)


@bdd_then(rx(rf"^стан {SOURCE} у {USER} записано в момент прогону$"))
def state_time(world: World, kind: str, ref: str, user: str) -> None:
    run = world.state(user, kind, ref)
    assert run.ran_at == world.clock.now()


@bdd_then(rx(rf"^у {USER} нема стану {SOURCE}$"))
def state_absent(world: World, user: str, kind: str, ref: str) -> None:
    assert world.find(user, kind, ref).id not in world.store.runs


@bdd_then(rx(rf"^у {USER} один рядок стану {SOURCE}$"))
def state_single(world: World, user: str, kind: str, ref: str) -> None:
    sub = world.find(user, kind, ref)
    assert [key for key in world.store.runs if key == sub.id] == [sub.id]


@bdd_then(rx(r"^усього рядків стану (?P<count>\d+)$"))
def state_rows(world: World, count: str) -> None:
    assert len(world.store.runs) == int(count)


@bdd_then(
    rx(
        rf"^під час читання {SOURCE} стан {WATCHED} у {USER} уже був збережений"
        r" разом з (?P<jobs>\d+) (?:вакансією|вакансіями)$"
    )
)
def seen_while_reading(
    world: World,
    kind: str,
    ref: str,
    watched_kind: str,
    watched_ref: str,
    user: str,
    jobs: str,
) -> None:
    assert world.seen.get(ref) == (True, int(jobs))


@bdd_then(rx(rf"^у {USER} нема ні джерела, ні стану {SOURCE}$"))
def source_and_state_gone(world: World, user: str, kind: str, ref: str) -> None:
    doomed = world.removed[(user, KINDS[kind], ref)]
    assert doomed.id not in world.store.subscriptions
    assert doomed.id not in world.store.runs
