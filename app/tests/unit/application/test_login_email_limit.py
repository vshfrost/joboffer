"""Ліміт входу за email: розподілений підбір пароля з багатьох IP упирається в нього, а блок має кінець."""

from datetime import datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.identity import CreateUser
from application.contracts.sessions import Login
from application.identity.sessions import SessionServices, SessionUseCases
from application.identity.use_cases import IdentityUseCases
from domain.identity.errors import InvalidCredentials, TooManyAttempts
from domain.identity.ids import SessionId, UserId
from domain.identity.session import Session, SessionPolicy
from domain.identity.user import User
from tests.support.clock import FakeClock
from tests.support.identity import FakePasswordHasher
from tests.support.ids import SequentialIds
from tests.support.sessions import InMemoryAuthUnitOfWork, SequentialTokens

EMAIL = "taras@example.com"
PASSWORD = "correct horse battery"
WRONG = "wrong password 123"
WINDOW = timedelta(minutes=15)


class Setup:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        users: dict[UserId, User] = {}
        sessions: dict[SessionId, Session] = {}
        failures: list[tuple[str, datetime]] = []

        def uow() -> InMemoryAuthUnitOfWork:
            return InMemoryAuthUnitOfWork(users, sessions, failures)

        identity = IdentityUseCases(uow, clock, ids, FakePasswordHasher())
        portal.call(
            identity.create_user,
            CreateUser(email=EMAIL, display_name="Богдан", password=PASSWORD),
        )
        self.sessions = SessionUseCases(
            uow,
            identity,
            SessionServices(
                clock=clock,
                ids=ids,
                tokens=SequentialTokens(),
                policy=SessionPolicy(
                    idle=timedelta(hours=12), absolute=timedelta(hours=48)
                ),
            ),
        )

    def attempt(self, password: str, *, ip: str, email: str = EMAIL) -> object:
        return self.portal.call(
            self.sessions.verify_login,
            Login(email=email, password=password, client=ip),
        )

    def fail_from_distinct_ips(self, count: int) -> None:
        for number in range(count):
            with pytest.raises(InvalidCredentials):
                self.attempt(WRONG, ip=f"10.0.{number // 250}.{number % 250 + 1}")


@pytest.fixture
def setup(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> Setup:
    return Setup(portal, clock, ids)


def test_twenty_failures_for_one_email_from_twenty_ips_throttle_a_new_ip(
    setup: Setup,
) -> None:
    setup.fail_from_distinct_ips(20)

    with pytest.raises(TooManyAttempts) as caught:
        setup.attempt(PASSWORD, ip="192.168.7.7")

    assert 0 < caught.value.retry_after <= 15 * 60


def test_nineteen_failures_from_distinct_ips_do_not_throttle(setup: Setup) -> None:
    setup.fail_from_distinct_ips(19)

    user = setup.attempt(PASSWORD, ip="192.168.7.7")

    assert getattr(user, "email", None) == EMAIL


def test_login_works_again_after_the_window(setup: Setup) -> None:
    setup.fail_from_distinct_ips(20)
    with pytest.raises(TooManyAttempts):
        setup.attempt(PASSWORD, ip="192.168.7.7")
    setup.clock.advance(WINDOW + timedelta(seconds=1))

    user = setup.attempt(PASSWORD, ip="192.168.7.7")

    assert getattr(user, "email", None) == EMAIL


def test_attempts_made_while_throttled_do_not_extend_the_block(setup: Setup) -> None:
    setup.fail_from_distinct_ips(20)
    setup.clock.advance(timedelta(minutes=10))
    for number in range(5):
        with pytest.raises(TooManyAttempts):
            setup.attempt(WRONG, ip=f"172.16.0.{number + 1}")
    setup.clock.advance(timedelta(minutes=5, seconds=1))

    user = setup.attempt(PASSWORD, ip="192.168.7.7")

    assert getattr(user, "email", None) == EMAIL


def test_failures_for_one_email_do_not_throttle_another_email(setup: Setup) -> None:
    setup.fail_from_distinct_ips(20)

    with pytest.raises(InvalidCredentials):
        setup.attempt(WRONG, ip="192.168.7.7", email="nobody@example.com")
