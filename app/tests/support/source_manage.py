"""In-memory керування джерелами: каталог поверх сховища прогону (ті самі підписки й стани),
unit of work з commit і пробний запит слагу, що запам'ятовує, про що питали."""

from collections.abc import Callable
from types import TracebackType
from typing import Self

from domain.identity.ids import UserId
from domain.sources.failure import FailureReason, SourceError
from domain.sources.ids import SourceId
from domain.sources.kinds import FeedSource, Platform
from domain.sources.manage import Company, CompanyRow, Feed, FeedRow
from domain.sources.run import SourceRun, Subscription
from tests.support.source_runs import SourceRunStore


class FakeProbe:
    """Пробний запит: слаг відомий, якщо його не названо в `failures`."""

    def __init__(self) -> None:
        self.checked: list[tuple[Platform, str]] = []
        self.failures: dict[tuple[Platform, str], FailureReason] = {}
        # Що відбувається посеред пробного запиту (напр. хтось додає ту саму компанію).
        self.during: dict[tuple[Platform, str], Callable[[], None]] = {}

    async def check(self, platform: Platform, slug: str) -> None:
        self.checked.append((platform, slug))
        if (platform, slug) in self.during:
            self.during[(platform, slug)]()
        if (platform, slug) in self.failures:
            raise SourceError(self.failures[(platform, slug)])


class InMemorySourceCatalog:
    def __init__(
        self,
        subscriptions: dict[SourceId, tuple[Subscription, bool]],
        runs: dict[SourceId, SourceRun],
    ) -> None:
        self._subscriptions = subscriptions
        self._runs = runs

    def _mine(self, user_id: UserId) -> list[tuple[Subscription, bool]]:
        return [
            (sub, enabled)
            for sub, enabled in self._subscriptions.values()
            if sub.user_id == user_id
        ]

    def _company(self, sub: Subscription, enabled: bool) -> CompanyRow:
        assert isinstance(sub.kind, Platform)
        company = Company(sub.id, sub.kind, sub.ref, sub.name, enabled)
        return CompanyRow(company, self._runs.get(sub.id))

    def _feed(self, sub: Subscription, enabled: bool) -> FeedRow:
        assert isinstance(sub.kind, FeedSource)
        return FeedRow(Feed(sub.id, sub.kind, sub.ref, enabled), self._runs.get(sub.id))

    def _find(
        self, user_id: UserId, source_id: SourceId, platform: bool
    ) -> tuple[Subscription, bool] | None:
        found = self._subscriptions.get(source_id)
        if found is None or found[0].user_id != user_id:
            return None
        return found if isinstance(found[0].kind, Platform) == platform else None

    async def companies(self, user_id: UserId) -> list[CompanyRow]:
        rows = [
            self._company(sub, enabled)
            for sub, enabled in self._mine(user_id)
            if isinstance(sub.kind, Platform)
        ]
        return sorted(
            rows, key=lambda row: (row.company.name.lower(), row.company.slug)
        )

    async def has_company(self, user_id: UserId, platform: Platform, slug: str) -> bool:
        return any(
            (sub.kind, sub.ref) == (platform, slug) for sub, _ in self._mine(user_id)
        )

    async def add_company(self, user_id: UserId, company: Company) -> bool:
        if await self.has_company(user_id, company.platform, company.slug):
            return False
        sub = Subscription(
            company.id, user_id, company.platform, company.slug, company.name
        )
        self._subscriptions[company.id] = (sub, company.enabled)
        return True

    async def set_company_enabled(
        self, user_id: UserId, source_id: SourceId, enabled: bool
    ) -> CompanyRow | None:
        found = self._find(user_id, source_id, platform=True)
        if found is None:
            return None
        self._subscriptions[source_id] = (found[0], enabled)
        return self._company(found[0], enabled)

    async def delete_company(self, user_id: UserId, source_id: SourceId) -> bool:
        return self._delete(user_id, source_id, platform=True)

    async def feeds(self, user_id: UserId) -> list[FeedRow]:
        rows = [
            self._feed(sub, enabled)
            for sub, enabled in self._mine(user_id)
            if isinstance(sub.kind, FeedSource)
        ]
        return sorted(rows, key=lambda row: (row.feed.source.value, row.feed.query))

    async def add_feed(self, user_id: UserId, feed: Feed) -> bool:
        if any(
            (sub.kind, sub.ref) == (feed.source, feed.query)
            for sub, _ in self._mine(user_id)
        ):
            return False
        sub = Subscription(feed.id, user_id, feed.source, feed.query)
        self._subscriptions[feed.id] = (sub, feed.enabled)
        return True

    async def set_feed_enabled(
        self, user_id: UserId, source_id: SourceId, enabled: bool
    ) -> FeedRow | None:
        found = self._find(user_id, source_id, platform=False)
        if found is None:
            return None
        self._subscriptions[source_id] = (found[0], enabled)
        return self._feed(found[0], enabled)

    async def delete_feed(self, user_id: UserId, source_id: SourceId) -> bool:
        return self._delete(user_id, source_id, platform=False)

    def _delete(self, user_id: UserId, source_id: SourceId, platform: bool) -> bool:
        if self._find(user_id, source_id, platform) is None:
            return False
        del self._subscriptions[source_id]
        # Як каскад у базі: стан прогону зникає разом із джерелом.
        self._runs.pop(source_id, None)
        return True


class InMemorySourceManageUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(self, store: SourceRunStore) -> None:
        self._store = store
        self._subscriptions: dict[SourceId, tuple[Subscription, bool]] | None = None
        self._runs: dict[SourceId, SourceRun] | None = None

    @property
    def source_catalog(self) -> InMemorySourceCatalog:
        if self._subscriptions is None or self._runs is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemorySourceCatalog(self._subscriptions, self._runs)

    async def __aenter__(self) -> Self:
        self._subscriptions = dict(self._store.subscriptions)
        self._runs = dict(self._store.runs)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._subscriptions = None
        self._runs = None

    async def commit(self) -> None:
        if self._subscriptions is None or self._runs is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        self._store.subscriptions = self._subscriptions
        self._store.runs = self._runs
