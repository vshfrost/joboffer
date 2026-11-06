"""SignupLimits на Postgres."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.identity.tables import SignupLimitRow


class PostgresSignupLimits:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def since(self, key: str, since: datetime) -> list[datetime]:
        result = await self._session.scalars(
            select(SignupLimitRow.hit_at)
            .where(SignupLimitRow.key == key, SignupLimitRow.hit_at >= since)
            .order_by(SignupLimitRow.hit_at)
        )
        return list(result)

    async def record(self, key: str, at: datetime) -> None:
        self._session.add(SignupLimitRow(key=key, hit_at=at))
        await self._session.flush()

    async def purge(self, before: datetime) -> None:
        await self._session.execute(
            delete(SignupLimitRow).where(SignupLimitRow.hit_at < before)
        )
