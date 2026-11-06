"""In-memory unit of work імпорту з джерел: вакансії (спільне сховище) й профілі користувачів."""

from types import TracebackType
from typing import Self

from domain.identity.ids import UserId
from domain.profile.profile import Profile
from tests.support.jobs import InMemoryJobs, InMemoryJobUnitOfWork, Store
from tests.support.profile import InMemoryProfiles


class InMemorySourceImportUnitOfWork:
    """Зміни вакансій видно лише після `commit()`; профілі імпорт не змінює."""

    def __init__(self, store: Store, profiles: dict[UserId, Profile]) -> None:
        self._inner = InMemoryJobUnitOfWork(store)
        self._profiles = profiles

    @property
    def jobs(self) -> InMemoryJobs:
        return self._inner.jobs

    @property
    def profiles(self) -> InMemoryProfiles:
        return InMemoryProfiles(self._profiles, {})

    async def __aenter__(self) -> Self:
        await self._inner.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._inner.__aexit__(exc_type, exc, traceback)

    async def commit(self) -> None:
        await self._inner.commit()
