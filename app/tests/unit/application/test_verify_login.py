"""Перевірка входу без сесії: той самий ліміт «клієнт + email», що й у `login`, але сесія не видається."""

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
WRONG = "wrong password 123"
CLIENT = "10.0.0.1"


class SpyHasher(FakePasswordHasher):
    def __init__(self) -> None:
        super().__init__()
        self.verified = 0

    async def verify(self, raw: str, stored: PasswordHash | None) -> bool:
        self.verified += 1
        return await super().verify(raw, stored)


class Setup:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.hasher = SpyHasher()
        self.stored_sessions: dict[SessionId, Session] = {}
        users: dict[UserId, User] = {}
        failures: list[tuple[str, datetime]] = []

        def uow() -> InMemoryAuthUnitOfWork:
            return InMemoryAuthUnitOfWork(users, self.stored_sessions, failures)

        identity = IdentityUseCases(uow, clock, ids, self.hasher)
        portal.call(
            identity.create_user,
            CreateUser(
                email="taras@example.com", display_name="Богдан", password=PASSWORD
            ),
        )
        self.hasher.verified = 0
        policy = SessionPolicy(idle=timedelta(hours=12), absolute=timedelta(hours=48))
        self.sessions = SessionUseCases(
            uow,
            identity,
            SessionServices(
                clock=clock, ids=ids, tokens=SequentialTokens(), policy=policy
            ),
        )

    def verify(
        self, password: str, email: str = "taras@example.com", client: str = CLIENT
    ) -> object:
        return self.portal.call(
            self.sessions.verify_login,
            Login(email=email, password=password, client=client),
        )

    def fail(self, times: int = 1) -> None:
        for _ in range(times):
            with pytest.raises(InvalidCredentials):
                self.verify(WRONG)


@pytest.fixture
def setup(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> Setup:
    return Setup(portal, clock, ids)


def test_correct_credentials_give_the_user_without_opening_a_session(
    setup: Setup,
) -> None:
    user = setup.verify(PASSWORD)

    assert getattr(user, "email", None) == "taras@example.com"
    assert setup.stored_sessions == {}


@pytest.mark.parametrize("email", ["taras@example.com", "nobody@example.com"])
def test_wrong_password_and_unknown_email_fail_the_same_way(
    setup: Setup, email: str
) -> None:
    with pytest.raises(InvalidCredentials):
        setup.verify(WRONG, email=email)


def test_fifth_failure_blocks_the_pair_with_retry_after(setup: Setup) -> None:
    setup.fail(LOGIN_MAX_FAILURES)

    with pytest.raises(TooManyAttempts) as caught:
        setup.verify(PASSWORD)

    assert caught.value.retry_after == 15 * 60


def test_blocked_attempt_does_not_hash_the_password(setup: Setup) -> None:
    setup.fail(LOGIN_MAX_FAILURES)
    before = setup.hasher.verified

    with pytest.raises(TooManyAttempts):
        setup.verify(PASSWORD)

    assert setup.hasher.verified == before


def test_failures_of_the_web_login_count_towards_the_same_limit(setup: Setup) -> None:
    for _ in range(LOGIN_MAX_FAILURES):
        with pytest.raises(InvalidCredentials):
            setup.portal.call(
                setup.sessions.login,
                Login(email="taras@example.com", password=WRONG, client=CLIENT),
            )

    with pytest.raises(TooManyAttempts):
        setup.verify(PASSWORD)


def test_other_client_or_other_email_is_not_blocked(setup: Setup) -> None:
    setup.fail(LOGIN_MAX_FAILURES)

    other_client = setup.verify(PASSWORD, client="10.0.0.2")

    assert getattr(other_client, "email", None) == "taras@example.com"
    with pytest.raises(InvalidCredentials):
        setup.verify(WRONG, email="other@example.com")


def test_success_resets_the_failure_count(setup: Setup) -> None:
    setup.fail(LOGIN_MAX_FAILURES - 1)
    setup.verify(PASSWORD)

    setup.fail(LOGIN_MAX_FAILURES - 1)
    assert getattr(setup.verify(PASSWORD), "email", None) == "taras@example.com"
