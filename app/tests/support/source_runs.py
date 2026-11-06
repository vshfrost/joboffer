"""In-memory прогін джерел: сховище підписок і станів, unit of work з локом, джерела-сценарії.

Зміни видно лише після `commit()`; лок прогону тримається, доки відкрита транзакція, що його взяла."""

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self

from application.ports.sources import SourceGone
from domain.identity.ids import UserId
from domain.profile.profile import Profile
from domain.sources.failure import FailureReason, SourceError
from domain.sources.ids import SourceId
from domain.sources.kinds import SourceKind
from domain.sources.posting import Posting
from domain.sources.run import SourceRun, Subscription
from domain.sources.target import SourceTarget
from tests.support.jobs import InMemoryJobs, Store
from tests.support.profile import InMemoryProfiles
from tests.support.sources import InMemorySourceImportUnitOfWork


@dataclass
class SourceRunStore:
    jobs: Store = field(default_factory=Store.empty)
    profiles: dict[UserId, Profile] = field(default_factory=dict)
    # Джерела користувачів у порядку створення: (підписка, увімкнене).
    subscriptions: dict[SourceId, tuple[Subscription, bool]] = field(
        default_factory=dict
    )
    runs: dict[SourceId, SourceRun] = field(default_factory=dict)
    # Запити «оновити зараз»: (користувач, коли запитано, коли виконано; None — чекає).
    refresh_requests: list[tuple[UserId, datetime, datetime | None]] = field(
        default_factory=list
    )
    # Лок прогону; живе поза транзакціями, як advisory lock у базі.
    locked: bool = False


class InMemorySourceRuns:
    def __init__(
        self,
        store: SourceRunStore,
        runs: dict[SourceId, SourceRun],
        hold: Callable[[], None],
    ) -> None:
        self._store = store
        self._runs = runs
        self._hold = hold

    async def lock(self) -> bool:
        if self._store.locked:
            return False
        self._store.locked = True
        self._hold()
        return True

    async def enabled(self) -> list[Subscription]:
        return [sub for sub, enabled in self._store.subscriptions.values() if enabled]

    async def save(self, subscription: Subscription, run: SourceRun) -> None:
        # Як зовнішній ключ у базі: стан джерела, якого вже нема, не зберегти.
        if subscription.id not in self._store.subscriptions:
            raise SourceGone
        self._runs[subscription.id] = run


class InMemorySourceRefreshRequests:
    def __init__(
        self, requests: list[tuple[UserId, datetime, datetime | None]]
    ) -> None:
        self._requests = requests

    async def since(self, user_id: UserId, moment: datetime) -> list[datetime]:
        return [
            at for owner, at, _ in self._requests if owner == user_id and at > moment
        ]

    async def add(self, user_id: UserId, requested_at: datetime) -> None:
        self._requests.append((user_id, requested_at, None))

    async def mark_handled(self, handled_at: datetime) -> int:
        pending = [i for i, (_, _, done) in enumerate(self._requests) if done is None]
        for i in pending:
            owner, at, _ = self._requests[i]
            self._requests[i] = (owner, at, handled_at)
        return len(pending)


class InMemorySourceRunUnitOfWork:
    """Вакансії й стани — після `commit()`; вихід без нього їх відкидає й відпускає лок."""

    def __init__(self, store: SourceRunStore) -> None:
        self._store = store
        self._inner = InMemorySourceImportUnitOfWork(store.jobs, store.profiles)
        self._runs: dict[SourceId, SourceRun] | None = None
        self._requests: list[tuple[UserId, datetime, datetime | None]] | None = None
        self._holds_lock = False

    @property
    def jobs(self) -> InMemoryJobs:
        return self._inner.jobs

    @property
    def profiles(self) -> InMemoryProfiles:
        return self._inner.profiles

    @property
    def source_runs(self) -> InMemorySourceRuns:
        if self._runs is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemorySourceRuns(self._store, self._runs, self._hold)

    @property
    def source_refresh_requests(self) -> InMemorySourceRefreshRequests:
        if self._requests is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemorySourceRefreshRequests(self._requests)

    def _hold(self) -> None:
        self._holds_lock = True

    async def __aenter__(self) -> Self:
        await self._inner.__aenter__()
        self._runs = dict(self._store.runs)
        self._requests = list(self._store.refresh_requests)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._holds_lock:
            self._store.locked = False
            self._holds_lock = False
        self._runs = None
        self._requests = None
        await self._inner.__aexit__(exc_type, exc, traceback)

    async def commit(self) -> None:
        if self._runs is None or self._requests is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        await self._inner.commit()
        self._store.runs = self._runs
        self._store.refresh_requests = self._requests


class ScriptedSource:
    """Адаптер-сценарій: віддає вакансії цілі чи кидає `SourceError`; запам'ятовує, що читали."""

    def __init__(self, reads: list[SourceTarget]) -> None:
        self._reads = reads
        self.postings: dict[str, list[Posting]] = {}
        self.failures: dict[str, FailureReason] = {}
        # Несподіваний збій читання: не `SourceError`, а будь-який інший виняток.
        self.crashes: dict[str, Exception] = {}
        # Що виконати посеред читання цілі (напр. запустити ще один прогін).
        self.during: dict[str, Callable[[], Awaitable[None]]] = {}

    async def fetch(self, target: SourceTarget) -> list[Posting]:
        self._reads.append(target)
        if target.ref in self.during:
            await self.during[target.ref]()
        if target.ref in self.crashes:
            raise self.crashes[target.ref]
        if target.ref in self.failures:
            raise SourceError(self.failures[target.ref])
        return list(self.postings.get(target.ref, []))


def registry(
    kinds: Iterable[SourceKind], reads: list[SourceTarget]
) -> dict[SourceKind, ScriptedSource]:
    return {kind: ScriptedSource(reads) for kind in kinds}
