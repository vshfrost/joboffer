"""PostgresUsers на справжній базі: та сама семантика, що в in-memory адаптера."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.identity.email import Email
from domain.identity.errors import EmailTaken
from domain.identity.ids import UserId
from domain.identity.password import PasswordHash
from domain.identity.user import DisplayName, User
from domain.shared.errors import NotFound
from infrastructure.db.unit_of_work import UnitOfWorkFactory, unit_of_work_factory

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def make_user(number: int, email: str, *, name: str = "Богдан") -> User:
    return User.register(
        id=UserId(UUID(int=number)),
        email=Email(email),
        display_name=DisplayName(name),
        password_hash=PasswordHash(f"$test${number}"),
        now=NOW,
    )


@pytest.fixture
def uow(portal: BlockingPortal, engine: AsyncEngine) -> UnitOfWorkFactory:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))

    portal.call(clean)
    return unit_of_work_factory(engine)


async def _add(uow: UnitOfWorkFactory, *users: User) -> None:
    async with uow() as tx:
        for user in users:
            await tx.users.add(user)
        await tx.commit()


def test_add_and_get_roundtrip(portal: BlockingPortal, uow: UnitOfWorkFactory) -> None:
    user = make_user(1, "taras@example.com")
    portal.call(_add, uow, user)

    async def get() -> User:
        async with uow() as tx:
            return await tx.users.get(user.id)

    assert portal.call(get) == user


def test_find_by_email(portal: BlockingPortal, uow: UnitOfWorkFactory) -> None:
    taras = make_user(1, "taras@example.com")
    katya = make_user(2, "katya@example.com", name="Наталя")
    portal.call(_add, uow, taras, katya)

    async def find(email: str) -> User | None:
        async with uow() as tx:
            return await tx.users.find_by_email(Email(email))

    assert portal.call(find, "katya@example.com") == katya
    assert portal.call(find, "taras@example.com") == taras
    assert portal.call(find, "nobody@example.com") is None


def test_second_user_with_same_email_is_rejected(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, make_user(1, "taras@example.com"))
    with pytest.raises(EmailTaken):
        portal.call(_add, uow, make_user(2, "taras@example.com"))


def test_rejected_duplicate_leaves_the_first_user_untouched(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = make_user(1, "taras@example.com")
    portal.call(_add, uow, first)
    with pytest.raises(EmailTaken):
        portal.call(_add, uow, make_user(2, "taras@example.com", name="Двійник"))

    async def get() -> User:
        async with uow() as tx:
            found = await tx.users.find_by_email(first.email)
            assert found is not None
            return found

    assert portal.call(get) == first


def test_missing_user(portal: BlockingPortal, uow: UnitOfWorkFactory) -> None:
    async def get() -> User:
        async with uow() as tx:
            return await tx.users.get(UserId(UUID(int=9)))

    with pytest.raises(NotFound):
        portal.call(get)


def test_add_without_commit_rolls_back(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def add_only() -> None:
        async with uow() as tx:
            await tx.users.add(make_user(1, "taras@example.com"))

    async def find() -> User | None:
        async with uow() as tx:
            return await tx.users.find_by_email(Email("taras@example.com"))

    portal.call(add_only)
    assert portal.call(find) is None
