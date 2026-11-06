"""PostgresSessions і PostgresLoginFailures на справжній базі: та сама семантика, що в in-memory."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.identity.email import Email
from domain.identity.ids import SessionId, UserId
from domain.identity.password import PasswordHash
from domain.identity.session import Session, SessionPolicy, TokenDigest
from domain.identity.user import DisplayName, User
from infrastructure.db.unit_of_work import UnitOfWorkFactory, unit_of_work_factory

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
POLICY = SessionPolicy(idle=timedelta(hours=1), absolute=timedelta(hours=24))
USER = UserId(UUID(int=1))


@pytest.fixture
def uow(portal: BlockingPortal, engine: AsyncEngine) -> UnitOfWorkFactory:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
            await conn.execute(text("TRUNCATE login_failures"))

    portal.call(clean)
    factory = unit_of_work_factory(engine)

    async def seed() -> None:
        async with factory() as tx:
            await tx.users.add(
                User.register(
                    id=USER,
                    email=Email("taras@example.com"),
                    display_name=DisplayName("Богдан"),
                    password_hash=PasswordHash("$test$"),
                    now=NOW,
                )
            )
            await tx.commit()

    portal.call(seed)
    return factory


def make_session(number: int, *, now: datetime = NOW) -> Session:
    return Session.start(
        id=SessionId(UUID(int=100 + number)),
        user_id=USER,
        token_digest=TokenDigest.from_token(f"token-{number}"),
        now=now,
        policy=POLICY,
    )


async def _add(uow: UnitOfWorkFactory, *sessions: Session) -> None:
    async with uow() as tx:
        for session in sessions:
            await tx.sessions.add(session)
        await tx.commit()


async def _find(uow: UnitOfWorkFactory, token: str) -> Session | None:
    async with uow() as tx:
        return await tx.sessions.find_by_digest(TokenDigest.from_token(token))


def test_add_and_find_roundtrip(portal: BlockingPortal, uow: UnitOfWorkFactory) -> None:
    session = make_session(1)
    portal.call(_add, uow, session)
    assert portal.call(_find, uow, "token-1") == session


def test_unknown_digest_is_none(portal: BlockingPortal, uow: UnitOfWorkFactory) -> None:
    portal.call(_add, uow, make_session(1))
    assert portal.call(_find, uow, "token-2") is None


def test_touch_updates_last_seen_only(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    session = make_session(1)
    portal.call(_add, uow, session)
    later = NOW + timedelta(minutes=30)

    async def touch() -> None:
        async with uow() as tx:
            await tx.sessions.touch(session.id, later)
            await tx.commit()

    portal.call(touch)
    assert portal.call(_find, uow, "token-1") == session.seen(later)


def test_delete_removes_one_session_and_ignores_unknown(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first, second = make_session(1), make_session(2)
    portal.call(_add, uow, first, second)

    async def delete(session_id: SessionId) -> None:
        async with uow() as tx:
            await tx.sessions.delete(session_id)
            await tx.commit()

    portal.call(delete, first.id)
    portal.call(delete, SessionId(UUID(int=999)))
    assert portal.call(_find, uow, "token-1") is None
    assert portal.call(_find, uow, "token-2") == second


def test_delete_expired_keeps_live_sessions(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    old = make_session(1)
    fresh = make_session(2, now=NOW + timedelta(hours=20))
    portal.call(_add, uow, old, fresh)

    async def purge() -> None:
        async with uow() as tx:
            await tx.sessions.delete_expired(NOW + timedelta(hours=24))
            await tx.commit()

    portal.call(purge)
    assert portal.call(_find, uow, "token-1") is None
    assert portal.call(_find, uow, "token-2") == fresh


def test_deleting_the_user_removes_the_sessions(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, make_session(1))

    async def delete_user() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM users"))

    portal.call(delete_user)
    assert portal.call(_find, uow, "token-1") is None


def test_session_added_without_commit_is_rolled_back(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def add_only() -> None:
        async with uow() as tx:
            await tx.sessions.add(make_session(1))

    portal.call(add_only)
    assert portal.call(_find, uow, "token-1") is None


async def _failures_since(
    uow: UnitOfWorkFactory, key: str, since: datetime
) -> list[datetime]:
    async with uow() as tx:
        return await tx.login_failures.since(key, since)


async def _record(uow: UnitOfWorkFactory, key: str, *times: datetime) -> None:
    async with uow() as tx:
        for at in times:
            await tx.login_failures.record(key, at)
        await tx.commit()


def test_failures_are_listed_oldest_first_within_the_window(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    minute = timedelta(minutes=1)
    portal.call(_record, uow, "k1", NOW + 3 * minute, NOW, NOW + minute)
    assert portal.call(_failures_since, uow, "k1", NOW + minute) == [
        NOW + minute,
        NOW + 3 * minute,
    ]


def test_failures_are_kept_per_key(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_record, uow, "k1", NOW)
    portal.call(_record, uow, "k2", NOW, NOW)
    assert len(portal.call(_failures_since, uow, "k1", NOW)) == 1
    assert len(portal.call(_failures_since, uow, "k2", NOW)) == 2


def test_clear_forgets_only_that_key(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_record, uow, "k1", NOW)
    portal.call(_record, uow, "k2", NOW)

    async def clear() -> None:
        async with uow() as tx:
            await tx.login_failures.clear("k1")
            await tx.commit()

    portal.call(clear)
    assert portal.call(_failures_since, uow, "k1", NOW) == []
    assert len(portal.call(_failures_since, uow, "k2", NOW)) == 1


def test_purge_forgets_old_failures_of_every_key(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    later = NOW + timedelta(minutes=20)
    portal.call(_record, uow, "k1", NOW, later)
    portal.call(_record, uow, "k2", NOW)

    async def purge() -> None:
        async with uow() as tx:
            await tx.login_failures.purge(NOW + timedelta(minutes=5))
            await tx.commit()

    portal.call(purge)
    assert portal.call(_failures_since, uow, "k1", NOW) == [later]
    assert portal.call(_failures_since, uow, "k2", NOW) == []
