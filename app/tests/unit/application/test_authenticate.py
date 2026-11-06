"""Вхід не розкриває, чи є такий email: перевірка пароля йде завжди, а пароль не потрапляє в логи."""

import logging
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.identity import Authenticate, CreateUser
from application.identity.use_cases import IdentityUseCases
from domain.identity.email import Email
from domain.identity.errors import InvalidCredentials
from domain.identity.ids import UserId
from domain.identity.password import PasswordHash
from domain.identity.user import DisplayName, User
from tests.support.clock import FakeClock
from tests.support.identity import FakePasswordHasher, InMemoryIdentityUnitOfWork
from tests.support.ids import SequentialIds

PASSWORD = "correct horse battery"


class SpyHasher(FakePasswordHasher):
    def __init__(self) -> None:
        super().__init__()
        self.verified: list[PasswordHash | None] = []

    async def verify(self, raw: str, stored: PasswordHash | None) -> bool:
        self.verified.append(stored)
        return await super().verify(raw, stored)


@pytest.fixture
def hasher() -> SpyHasher:
    return SpyHasher()


@pytest.fixture
def store() -> dict[UserId, User]:
    return {}


@pytest.fixture
def identity(
    store: dict[UserId, User], clock: FakeClock, ids: SequentialIds, hasher: SpyHasher
) -> IdentityUseCases:
    return IdentityUseCases(
        lambda: InMemoryIdentityUnitOfWork(store), clock, ids, hasher
    )


@pytest.fixture
def registered(
    portal: BlockingPortal,
    store: dict[UserId, User],
    hasher: SpyHasher,
    clock: FakeClock,
) -> None:
    """Користувач у сховищі напряму, повз use case, який перевіряє ці тести."""
    user = User(
        id=UserId(UUID(int=100)),
        email=Email("taras@example.com"),
        display_name=DisplayName("Богдан"),
        password_hash=portal.call(hasher.hash, PASSWORD),
        version=1,
        created_at=clock.now(),
    )
    store[user.id] = user


def attempt(
    portal: BlockingPortal, identity: IdentityUseCases, email: str, password: str
) -> None:
    command = Authenticate(email=email, password=password)
    with pytest.raises(InvalidCredentials):
        portal.call(identity.authenticate, command)


@pytest.mark.usefixtures("registered")
@pytest.mark.parametrize("email", ["nobody@example.com", "not-an-email"])
def test_unknown_or_malformed_email_still_verifies_a_password(
    portal: BlockingPortal, identity: IdentityUseCases, hasher: SpyHasher, email: str
) -> None:
    attempt(portal, identity, email, PASSWORD)
    assert hasher.verified == [None]


@pytest.mark.usefixtures("registered")
def test_known_email_verifies_against_the_stored_hash(
    portal: BlockingPortal,
    identity: IdentityUseCases,
    hasher: SpyHasher,
    store: dict[UserId, User],
) -> None:
    attempt(portal, identity, "taras@example.com", "wrong password 123")
    (stored,) = [user.password_hash for user in store.values()]
    assert hasher.verified == [stored]


@pytest.mark.usefixtures("registered")
def test_oversized_password_is_rejected_without_hashing(
    portal: BlockingPortal, identity: IdentityUseCases, hasher: SpyHasher
) -> None:
    attempt(portal, identity, "taras@example.com", "x" * 1025)
    assert hasher.verified == []


def test_passwords_never_reach_the_logs(
    portal: BlockingPortal,
    identity: IdentityUseCases,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        portal.call(
            identity.create_user,
            CreateUser(
                email="taras@example.com", display_name="Богдан", password=PASSWORD
            ),
        )
        attempt(portal, identity, "taras@example.com", "wrong password 123")
    assert PASSWORD not in caplog.text
    assert "wrong password 123" not in caplog.text


@pytest.mark.usefixtures("registered")
def test_authenticate_returns_the_same_view_each_time(
    portal: BlockingPortal, identity: IdentityUseCases
) -> None:
    command = Authenticate(email="taras@example.com", password=PASSWORD)
    first = portal.call(identity.authenticate, command)
    second = portal.call(identity.authenticate, command)
    assert first == second
