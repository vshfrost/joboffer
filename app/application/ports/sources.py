"""Порти імпорту вакансій із джерел і прогону джерел: вакансії, профіль і стан прогону в одній транзакції."""

from datetime import datetime
from typing import Protocol

from application.ports.jobs import JobRepository
from application.ports.profile import ProfileRepository
from application.ports.unit_of_work import UnitOfWork
from domain.identity.ids import UserId
from domain.sources.ids import SourceId
from domain.sources.kinds import Platform
from domain.sources.manage import Company, CompanyRow, Feed, FeedRow
from domain.sources.run import SourceRun, Subscription


class SourceImportUnitOfWork(UnitOfWork, Protocol):
    @property
    def jobs(self) -> JobRepository: ...

    @property
    def profiles(self) -> ProfileRepository: ...


class SourceGone(Exception):
    """Джерело видалено, поки його читали: стан прогону зберегти нікуди."""


class SourceRunRepository(Protocol):
    async def lock(self) -> bool:
        """Бере лок прогону до кінця транзакції; `False` — прогін уже йде в іншому процесі."""
        ...

    async def enabled(self) -> list[Subscription]:
        """Увімкнені компанії й стрічки всіх користувачів; вимкнені не повертаються."""
        ...

    async def save(self, subscription: Subscription, run: SourceRun) -> None:
        """Стан джерела користувача: один рядок на джерело, новий прогін замінює попередній.
        `SourceGone` — джерело вже видалено."""
        ...


class SourceRefreshRequestRepository(Protocol):
    async def since(self, user_id: UserId, moment: datetime) -> list[datetime]:
        """Коли користувач запитував «оновити зараз» після `moment`."""
        ...

    async def add(self, user_id: UserId, requested_at: datetime) -> None: ...

    async def mark_handled(self, handled_at: datetime) -> int:
        """Позначає виконаними всі запити, що чекали, усіх користувачів; повертає скільки."""
        ...


class SourceRunUnitOfWork(SourceImportUnitOfWork, Protocol):
    @property
    def source_runs(self) -> SourceRunRepository: ...

    @property
    def source_refresh_requests(self) -> SourceRefreshRequestRepository: ...


class SourceCatalog(Protocol):
    """Джерела одного користувача: список зі станом останнього прогону, додати, вимкнути, видалити.
    Чужого джерела тут не існує: пошук і зміна йдуть за парою «користувач + id»."""

    async def companies(self, user_id: UserId) -> list[CompanyRow]: ...

    async def has_company(
        self, user_id: UserId, platform: Platform, slug: str
    ) -> bool: ...

    async def add_company(self, user_id: UserId, company: Company) -> bool:
        """`False` — така компанія (платформа + слаг) у користувача вже є."""
        ...

    async def set_company_enabled(
        self, user_id: UserId, source_id: SourceId, enabled: bool
    ) -> CompanyRow | None:
        """`None` — компанії нема чи вона чужа."""
        ...

    async def delete_company(self, user_id: UserId, source_id: SourceId) -> bool:
        """Прибирає компанію й стан її прогону; імпортовані вакансії лишаються.
        `False` — компанії нема чи вона чужа."""
        ...

    async def feeds(self, user_id: UserId) -> list[FeedRow]: ...

    async def add_feed(self, user_id: UserId, feed: Feed) -> bool:
        """`False` — така стрічка (джерело + запит) у користувача вже є."""
        ...

    async def set_feed_enabled(
        self, user_id: UserId, source_id: SourceId, enabled: bool
    ) -> FeedRow | None: ...

    async def delete_feed(self, user_id: UserId, source_id: SourceId) -> bool: ...


class SourceManageUnitOfWork(UnitOfWork, Protocol):
    @property
    def source_catalog(self) -> SourceCatalog: ...


class SourceOverviewUnitOfWork(SourceImportUnitOfWork, Protocol):
    """Усе, що бачить сторінка джерел: каталог, запити «оновити зараз», вакансії й профіль."""

    @property
    def source_catalog(self) -> SourceCatalog: ...

    @property
    def source_refresh_requests(self) -> SourceRefreshRequestRepository: ...
