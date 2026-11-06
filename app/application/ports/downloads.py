"""Порти одноразових посилань на PDF: репозиторій посилань і unit of work, що його відкриває."""

from datetime import datetime
from typing import Protocol

from application.ports.documents import DocumentRepository
from application.ports.profile import ProfileRepository
from application.ports.unit_of_work import UnitOfWork
from domain.documents.download import DownloadGrant
from domain.documents.ids import DocumentId
from domain.identity.ids import UserId
from domain.identity.session import TokenDigest


class DownloadLinkRepository(Protocol):
    async def add(
        self,
        user_id: UserId,
        document_id: DocumentId,
        digest: TokenDigest,
        expires_at: datetime,
    ) -> None:
        """Зберігає лише дайджест токена."""
        ...

    async def redeem(self, digest: TokenDigest, now: datetime) -> DownloadGrant | None:
        """Атомарно позначає посилання використаним і повертає, кому воно відкриває файл.
        None — токена нема, його вже використано чи строк минув (`now >= expires_at`)."""
        ...


class DownloadUnitOfWork(UnitOfWork, Protocol):
    @property
    def documents(self) -> DocumentRepository: ...

    @property
    def profiles(self) -> ProfileRepository: ...

    @property
    def download_links(self) -> DownloadLinkRepository: ...
