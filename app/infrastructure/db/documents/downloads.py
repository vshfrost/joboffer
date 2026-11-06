"""DownloadLinkRepository на Postgres: у базі лише sha256-дайджест токена."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.documents.download import DownloadGrant
from domain.documents.ids import DocumentId
from domain.identity.ids import UserId
from domain.identity.session import TokenDigest
from infrastructure.db.documents.tables import DocumentDownloadLinkRow, DocumentRow


class PostgresDownloadLinks:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        user_id: UserId,
        document_id: DocumentId,
        digest: TokenDigest,
        expires_at: datetime,
    ) -> None:
        self._session.add(
            DocumentDownloadLinkRow(
                token_digest=digest.value,
                user_id=user_id.value,
                document_id=document_id.value,
                expires_at=expires_at,
                used_at=None,
            )
        )
        await self._session.flush()

    async def redeem(self, digest: TokenDigest, now: datetime) -> DownloadGrant | None:
        # Один UPDATE: паралельний запит чекає на рядок і після commit уже не підпадає під умову.
        claimed = (
            await self._session.execute(
                update(DocumentDownloadLinkRow)
                .where(
                    DocumentDownloadLinkRow.token_digest == digest.value,
                    DocumentDownloadLinkRow.used_at.is_(None),
                    DocumentDownloadLinkRow.expires_at > now,
                )
                .values(used_at=now)
                .returning(
                    DocumentDownloadLinkRow.user_id,
                    DocumentDownloadLinkRow.document_id,
                )
            )
        ).first()
        if claimed is None:
            return None
        number = (
            await self._session.execute(
                select(DocumentRow.document_number).where(
                    DocumentRow.id == claimed.document_id
                )
            )
        ).scalar_one()
        return DownloadGrant(UserId(claimed.user_id), number)
