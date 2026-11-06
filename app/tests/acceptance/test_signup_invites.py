"""Кроки для features/signup_invites.feature: use cases запрошень + in-memory адаптери через портал."""

import hashlib
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given, parsers, scenarios, then, when

from application.contracts.invites import CheckInvite, InviteIssued, InviteStatus
from application.identity.invites import SignupInviteUseCases
from domain.identity.errors import TooManyAttempts
from domain.identity.ids import SignupInviteId
from domain.identity.invite import SignupInvite
from domain.identity.signup import SignupMode
from domain.shared.errors import DomainError
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.invites import InMemoryInviteUnitOfWork
from tests.support.sessions import SequentialTokens

scenarios("features/signup_invites.feature")


class Stores:
    def __init__(self) -> None:
        self.invites: dict[SignupInviteId, SignupInvite] = {}
        self.failures: list[tuple[str, datetime]] = []


class Outcome:
    def __init__(self) -> None:
        self.issued: InviteIssued | None = None
        self.created_at: datetime | None = None
        self.status: InviteStatus | None = None
        self.errors: list[DomainError] = []

    def run[T](
        self, portal: BlockingPortal, action: Callable[[], Awaitable[T]]
    ) -> T | None:
        try:
            return portal.call(action)
        except DomainError as error:
            self.errors.append(error)
            return None


class Settings:
    mode = SignupMode.CLOSED


@pytest.fixture
def stores() -> Stores:
    return Stores()


@pytest.fixture
def outcome() -> Outcome:
    return Outcome()


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def invites(
    stores: Stores, clock: FakeClock, ids: SequentialIds, settings: Settings
) -> SignupInviteUseCases:
    return SignupInviteUseCases(
        lambda: InMemoryInviteUnitOfWork(stores.invites, stores.failures),
        clock,
        ids,
        SequentialTokens(),
        settings.mode,
    )


@given("реєстрація працює за запрошенням")
def signup_by_invite(settings: Settings) -> None:
    settings.mode = SignupMode.INVITE


@given("реєстрація закрита")
def signup_closed(settings: Settings) -> None:
    settings.mode = SignupMode.CLOSED


@when("оператор створює запрошення")
def operator_creates(
    portal: BlockingPortal,
    invites: SignupInviteUseCases,
    outcome: Outcome,
    clock: FakeClock,
) -> None:
    outcome.created_at = clock.now()
    outcome.issued = outcome.run(portal, invites.create)


def _check(
    portal: BlockingPortal,
    invites: SignupInviteUseCases,
    outcome: Outcome,
    token: str,
    client: str,
) -> None:
    command = CheckInvite(token=token, client=client)
    outcome.status = outcome.run(portal, lambda: invites.check(command))


@when(parsers.parse('я перевіряю запрошення з клієнта "{client}"'))
def check_issued(
    portal: BlockingPortal,
    invites: SignupInviteUseCases,
    outcome: Outcome,
    client: str,
) -> None:
    assert outcome.issued is not None
    _check(portal, invites, outcome, outcome.issued.token, client)


@when(parsers.parse('я перевіряю запрошення {count:d} разів з клієнта "{client}"'))
def check_many(
    portal: BlockingPortal,
    invites: SignupInviteUseCases,
    outcome: Outcome,
    count: int,
    client: str,
) -> None:
    assert outcome.issued is not None
    for _ in range(count):
        _check(portal, invites, outcome, outcome.issued.token, client)


@when(parsers.parse('я перевіряю токен "{token}" з клієнта "{client}"'))
def check_token(
    portal: BlockingPortal,
    invites: SignupInviteUseCases,
    outcome: Outcome,
    token: str,
    client: str,
) -> None:
    _check(portal, invites, outcome, token, client)


@when(parsers.parse('я перевіряю порожній токен з клієнта "{client}"'))
def check_empty(
    portal: BlockingPortal,
    invites: SignupInviteUseCases,
    outcome: Outcome,
    client: str,
) -> None:
    _check(portal, invites, outcome, "", client)


@when(
    parsers.parse('я перевіряю токен довжиною {size:d} символів з клієнта "{client}"')
)
def check_long(
    portal: BlockingPortal,
    invites: SignupInviteUseCases,
    outcome: Outcome,
    size: int,
    client: str,
) -> None:
    _check(portal, invites, outcome, "x" * size, client)


@when("я погашаю запрошення")
def redeem(
    portal: BlockingPortal, invites: SignupInviteUseCases, outcome: Outcome
) -> None:
    assert outcome.issued is not None
    token = outcome.issued.token
    outcome.run(portal, lambda: invites.redeem(token))


@when(parsers.parse("минає {days:d} днів і {minutes:d} хвилина"))
def pass_days_and_minute(clock: FakeClock, days: int, minutes: int) -> None:
    clock.advance(timedelta(days=days, minutes=minutes))


@when(parsers.parse("минає {days:d} днів і {hours:d} години"))
def pass_days_and_hours(clock: FakeClock, days: int, hours: int) -> None:
    clock.advance(timedelta(days=days, hours=hours))


@when(parsers.parse("минає {minutes:d} хвилин"))
def pass_minutes(clock: FakeClock, minutes: int) -> None:
    clock.advance(timedelta(minutes=minutes))


@then("запрошення дійсне до 7 днів від створення")
def valid_for_seven_days(outcome: Outcome) -> None:
    assert outcome.errors == []
    assert outcome.created_at is not None
    assert outcome.status == InviteStatus(
        valid=True, expires_at=outcome.created_at + timedelta(days=7)
    )


@then("у сховищі запрошень лише sha256 токена")
def only_digest_stored(outcome: Outcome, stores: Stores) -> None:
    assert outcome.issued is not None
    token = outcome.issued.token
    assert token
    (stored,) = stores.invites.values()
    assert stored.token_digest.value == hashlib.sha256(token.encode()).hexdigest()
    assert token not in repr(stored)


@then(parsers.parse('отримую помилку "{code}"'))
def got_error(outcome: Outcome, code: str) -> None:
    assert [error.code for error in outcome.errors] == [code]


@then(parsers.parse('отримую помилку "{code}" з очікуванням {seconds:d} секунд'))
def got_throttled(outcome: Outcome, code: str, seconds: int) -> None:
    assert [error.code for error in outcome.errors] == [code]
    error = outcome.errors[0]
    assert isinstance(error, TooManyAttempts)
    assert error.retry_after == seconds


@then("жодної помилки")
def no_errors(outcome: Outcome) -> None:
    assert outcome.errors == []
