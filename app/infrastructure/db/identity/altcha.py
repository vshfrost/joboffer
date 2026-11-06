"""SolvedAltchas на Postgres. Одноразовість гарантує первинний ключ, а не попередня перевірка."""

from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.identity.tables import AltchaSolutionRow


class PostgresSolvedAltchas:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, signature: str, expires_at: datetime) -> bool:
        inserted = await self._session.scalar(
            insert(AltchaSolutionRow)
            .values(signature=signature, expires_at=expires_at)
            .on_conflict_do_nothing()
            .returning(AltchaSolutionRow.signature)
        )
        return inserted is not None

    async def purge(self, now: datetime) -> None:
        await self._session.execute(
            delete(AltchaSolutionRow).where(AltchaSolutionRow.expires_at < now)
        )
