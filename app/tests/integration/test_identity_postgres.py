"""Identity наскрізь: use cases + справжній Argon2 + Postgres."""

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.identity import Authenticate, CreateUser
from application.identity.use_cases import IdentityUseCases
from domain.identity.errors import EmailTaken, InvalidCredentials
from infrastructure.db.unit_of_work import unit_of_work_factory
from infrastructure.security.passwords import Argon2PasswordHasher
from infrastructure.system import RandomIds, SystemClock

PASSWORD = "correct horse battery"


@pytest.fixture
def identity(portal: BlockingPortal, engine: AsyncEngine) -> IdentityUseCases:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))

    portal.call(clean)
    return IdentityUseCases(
        unit_of_work_factory(engine), SystemClock(), RandomIds(), Argon2PasswordHasher()
    )


def create(email: str, name: str, password: str = PASSWORD) -> CreateUser:
    return CreateUser(email=email, display_name=name, password=password)


def test_created_user_can_log_in(
    portal: BlockingPortal, identity: IdentityUseCases
) -> None:
    created = portal.call(identity.create_user, create("Taras@Example.com", "Богдан"))
    logged_in = portal.call(
        identity.authenticate,
        Authenticate(email="taras@example.com", password=PASSWORD),
    )
    assert logged_in == created
    assert created.email == "taras@example.com"


def test_wrong_password_and_unknown_email_are_rejected(
    portal: BlockingPortal, identity: IdentityUseCases
) -> None:
    portal.call(identity.create_user, create("taras@example.com", "Богдан"))
    for email, password in [
        ("taras@example.com", "wrong password 123"),
        ("nobody@example.com", PASSWORD),
    ]:
        with pytest.raises(InvalidCredentials):
            portal.call(
                identity.authenticate, Authenticate(email=email, password=password)
            )


def test_duplicate_email_is_rejected(
    portal: BlockingPortal, identity: IdentityUseCases
) -> None:
    portal.call(identity.create_user, create("taras@example.com", "Богдан"))
    with pytest.raises(EmailTaken):
        portal.call(identity.create_user, create("TARAS@example.com", "Двійник"))


def test_database_stores_only_an_argon2id_hash(
    portal: BlockingPortal, engine: AsyncEngine, identity: IdentityUseCases
) -> None:
    portal.call(identity.create_user, create("taras@example.com", "Богдан"))

    async def stored() -> str:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT password_hash FROM users"))
            return str(result.scalar_one())

    value = portal.call(stored)
    assert value.startswith("$argon2id$")
    assert PASSWORD not in value


def test_users_are_isolated(portal: BlockingPortal, identity: IdentityUseCases) -> None:
    taras = portal.call(identity.create_user, create("taras@example.com", "Богдан"))
    katya = portal.call(
        identity.create_user,
        create("katya@example.com", "Наталя", "another long password"),
    )
    assert taras.id != katya.id
    with pytest.raises(InvalidCredentials):
        portal.call(
            identity.authenticate,
            Authenticate(email="taras@example.com", password="another long password"),
        )
    logged_in = portal.call(
        identity.authenticate,
        Authenticate(email="katya@example.com", password="another long password"),
    )
    assert logged_in.id == katya.id
