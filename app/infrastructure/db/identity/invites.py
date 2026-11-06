"""SignupInviteRepository на Postgres."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.identity.ids import SignupInviteId
from domain.identity.invite import SignupInvite
from domain.identity.session import TokenDigest
from infrastructure.db.identity.tables import SignupInviteRow


def _to_domain(row: SignupInviteRow) -> SignupInvite:
    return SignupInvite(
        id=SignupInviteId(row.id),
        token_digest=TokenDigest(row.token_digest),
        created_at=row.created_at,
        expires_at=row.expires_at,
        used_at=row.used_at,
    )


class PostgresSignupInvites:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, invite: SignupInvite) -> None:
        self._session.add(
            SignupInviteRow(
                id=invite.id.value,
                token_digest=invite.token_digest.value,
                created_at=invite.created_at,
                expires_at=invite.expires_at,
                used_at=invite.used_at,
            )
        )
        await self._session.flush()

    async def find_by_digest(self, digest: TokenDigest) -> SignupInvite | None:
        row = await self._session.scalar(
            select(SignupInviteRow).where(SignupInviteRow.token_digest == digest.value)
        )
        return None if row is None else _to_domain(row)

    async def redeem(self, digest: TokenDigest, now: datetime) -> bool:
        # Один UPDATE з умовою: конкурентний другий чекає на рядок і не знаходить `used_at IS NULL`.
        redeemed = await self._session.scalar(
            update(SignupInviteRow)
            .where(
                SignupInviteRow.token_digest == digest.value,
                SignupInviteRow.used_at.is_(None),
                SignupInviteRow.expires_at > now,
            )
            .values(used_at=now)
            .returning(SignupInviteRow.id)
        )
        return redeemed is not None
