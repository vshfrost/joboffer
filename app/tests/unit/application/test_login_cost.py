"""Заблокований вхід дешевий: пароль не хешується, а невдачі рахуються до ліміту."""

from datetime import datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.identity import CreateUser
from application.contracts.sessions import Login
from application.identity.sessions import (
    LOGIN_MAX_FAILURES,
    SessionServices,
    SessionUseCases,
)
from application.identity.use_cases import IdentityUseCases
from domain.identity.errors import InvalidCredentials, TooManyAttempts
from domain.identity.ids import SessionId, UserId
from domain.identity.password import PasswordHash
from domain.identity.session import Session, SessionPolicy
from domain.identity.user import User
from tests.support.clock import FakeClock
from tests.support.identity import FakePasswordHasher
from tests.support.ids import SequentialIds
from tests.support.sessions import InMemoryAuthUnitOfWork, SequentialTokens

PASSWORD = "correct horse battery"


class SpyHasher(FakePasswordHasher):
    def __init__(self) -> None:
        super().__init__()
        self.verified = 0

    async def verify(self, raw: str, stored: PasswordHash | None) -> bool:
        self.verified += 1
        return await super().verify(raw, stored)


@pytest.fixture
def hasher() -> SpyHasher:
    return SpyHasher()


@pytest.fixture
def sessions(
    portal: BlockingPortal, clock: FakeClock, ids: SequentialIds, hasher: SpyHasher
) -> SessionUseCases:
    users: dict[UserId, User] = {}
    stored_sessions: dict[SessionId, Session] = {}
    failures: list[tuple[str, datetime]] = []

    def uow() -> InMemoryAuthUnitOfWork:
        return InMemoryAuthUnitOfWork(users, stored_sessions, failures)

    identity = IdentityUseCases(uow, clock, ids, hasher)
    portal.call(
        identity.create_user,
        CreateUser(email="taras@example.com", display_name="Богдан", password=PASSWORD),
    )
    hasher.verified = 0
    policy = SessionPolicy(idle=timedelta(hours=12), absolute=timedelta(hours=48))
    return SessionUseCases(
        uow,
        identity,
        SessionServices(clock=clock, ids=ids, tokens=SequentialTokens(), policy=policy),
    )


def attempt(portal: BlockingPortal, sessions: SessionUseCases, password: str) -> None:
    command = Login(email="taras@example.com", password=password, client="10.0.0.1")
    portal.call(sessions.login, command)


def test_blocked_login_does_not_hash_the_password(
    portal: BlockingPortal, sessions: SessionUseCases, hasher: SpyHasher
) -> None:
    for _ in range(LOGIN_MAX_FAILURES):
        with pytest.raises(InvalidCredentials):
            attempt(portal, sessions, "wrong password 123")
    verified_before = hasher.verified
    with pytest.raises(TooManyAttempts):
        attempt(portal, sessions, PASSWORD)
    assert hasher.verified == verified_before


def test_limit_is_five_failures() -> None:
    assert LOGIN_MAX_FAILURES == 5
