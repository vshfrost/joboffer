"""SessionRepository і LoginFailures на Postgres."""

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.identity.ids import SessionId, UserId
from domain.identity.session import Session, TokenDigest
from infrastructure.db.identity.tables import LoginFailureRow, SessionRow


def _to_domain(row: SessionRow) -> Session:
    return Session(
        id=SessionId(row.id),
        user_id=UserId(row.user_id),
        token_digest=TokenDigest(row.token_digest),
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        expires_at=row.expires_at,
    )


class PostgresSessions:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: Session) -> None:
        self._session.add(
            SessionRow(
                id=session.id.value,
                user_id=session.user_id.value,
                token_digest=session.token_digest.value,
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
                expires_at=session.expires_at,
            )
        )
        await self._session.flush()

    async def find_by_digest(self, digest: TokenDigest) -> Session | None:
        row = await self._session.scalar(
            select(SessionRow).where(SessionRow.token_digest == digest.value)
        )
        return None if row is None else _to_domain(row)

    async def touch(self, session_id: SessionId, at: datetime) -> None:
        await self._session.execute(
            update(SessionRow)
            .where(SessionRow.id == session_id.value)
            .values(last_seen_at=at)
        )

    async def delete(self, session_id: SessionId) -> None:
        await self._session.execute(
            delete(SessionRow).where(SessionRow.id == session_id.value)
        )

    async def delete_expired(self, now: datetime) -> None:
        await self._session.execute(
            delete(SessionRow).where(SessionRow.expires_at <= now)
        )


class PostgresLoginFailures:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def since(self, key: str, since: datetime) -> list[datetime]:
        rows = await self._session.scalars(
            select(LoginFailureRow.failed_at)
            .where(LoginFailureRow.key == key, LoginFailureRow.failed_at >= since)
            .order_by(LoginFailureRow.failed_at)
        )
        return list(rows)

    async def record(self, key: str, at: datetime) -> None:
        self._session.add(LoginFailureRow(key=key, failed_at=at))
        await self._session.flush()

    async def clear(self, key: str) -> None:
        await self._session.execute(
            delete(LoginFailureRow).where(LoginFailureRow.key == key)
        )

    async def purge(self, before: datetime) -> None:
        await self._session.execute(
            delete(LoginFailureRow).where(LoginFailureRow.failed_at < before)
        )
