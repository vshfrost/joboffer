"""Зовнішні identity й користувачі без пароля на справжній базі."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.identity.email import Email
from domain.identity.external_identity import GOOGLE, ExternalIdentity
from domain.identity.ids import ExternalIdentityId, UserId
from domain.identity.user import DisplayName, User
from infrastructure.db.unit_of_work import UnitOfWorkFactory, unit_of_work_factory

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
USER = UserId(UUID(int=1))
OTHER = UserId(UUID(int=2))


@pytest.fixture
def uow(portal: BlockingPortal, engine: AsyncEngine) -> UnitOfWorkFactory:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))

    portal.call(clean)
    return unit_of_work_factory(engine)


def make_user(user_id: UserId, email: str) -> User:
    return User.register(
        id=user_id,
        email=Email(email),
        display_name=DisplayName("Богдан"),
        password_hash=None,
        now=NOW,
    )


def make_identity(
    number: int, user_id: UserId = USER, subject: str = "sub-1"
) -> ExternalIdentity:
    return ExternalIdentity(
        id=ExternalIdentityId(UUID(int=100 + number)),
        provider=GOOGLE,
        subject=subject,
        user_id=user_id,
        created_at=NOW,
    )


def test_user_without_a_password_roundtrips(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> User:
        async with uow() as tx:
            await tx.users.add(make_user(USER, "taras@example.com"))
            await tx.commit()
        async with uow() as tx:
            return await tx.users.get(USER)

    assert portal.call(run).password_hash is None


def test_identity_roundtrips_by_provider_and_subject(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    identity = make_identity(1)

    async def run() -> tuple[
        ExternalIdentity | None, ExternalIdentity | None, ExternalIdentity | None
    ]:
        async with uow() as tx:
            await tx.users.add(make_user(USER, "taras@example.com"))
            await tx.external_identities.add(identity)
            await tx.commit()
        async with uow() as tx:
            return (
                await tx.external_identities.find(GOOGLE, "sub-1"),
                await tx.external_identities.find(GOOGLE, "other-sub"),
                await tx.external_identities.find("apple", "sub-1"),
            )

    assert portal.call(run) == (identity, None, None)


def test_the_same_provider_subject_cannot_belong_to_two_users(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> None:
        async with uow() as tx:
            await tx.users.add(make_user(USER, "taras@example.com"))
            await tx.users.add(make_user(OTHER, "katya@example.com"))
            await tx.external_identities.add(make_identity(1, USER))
            await tx.external_identities.add(make_identity(2, OTHER))

    with pytest.raises(IntegrityError):
        portal.call(run)


def test_deleting_the_user_deletes_the_identities(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    async def run() -> int:
        async with uow() as tx:
            await tx.users.add(make_user(USER, "taras@example.com"))
            await tx.external_identities.add(make_identity(1))
            await tx.commit()
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM users"))
            result = await conn.execute(text("SELECT count(*) FROM user_identities"))
            return int(result.scalar_one())

    assert portal.call(run) == 0
