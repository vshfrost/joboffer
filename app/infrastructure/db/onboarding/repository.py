"""OnboardingTips на Postgres. Повтор не міняє стану: `ON CONFLICT` лишає перші часи."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.identity.ids import UserId
from domain.onboarding.steps import TipState
from infrastructure.db.onboarding.tables import OnboardingTipRow


class PostgresOnboardingTips:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self, user_id: UserId) -> list[TipState]:
        rows = await self._session.scalars(
            select(OnboardingTipRow).where(OnboardingTipRow.user_id == user_id.value)
        )
        return [TipState(row.tip_key, row.seen_at, row.dismissed_at) for row in rows]

    async def mark_seen(self, user_id: UserId, key: str, now: datetime) -> None:
        await self._session.execute(
            pg_insert(OnboardingTipRow)
            .values(user_id=user_id.value, tip_key=key, seen_at=now)
            .on_conflict_do_nothing(
                index_elements=[OnboardingTipRow.user_id, OnboardingTipRow.tip_key]
            )
        )

    async def dismiss(self, user_id: UserId, key: str, now: datetime) -> None:
        insert = pg_insert(OnboardingTipRow).values(
            user_id=user_id.value, tip_key=key, seen_at=now, dismissed_at=now
        )
        await self._session.execute(
            insert.on_conflict_do_update(
                index_elements=[OnboardingTipRow.user_id, OnboardingTipRow.tip_key],
                set_={"dismissed_at": insert.excluded.dismissed_at},
                where=OnboardingTipRow.dismissed_at.is_(None),
            )
        )
