"""Кроки для features/sessions.feature: use cases сесій + in-memory адаптери через портал."""

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given, parsers, scenarios, then, when

from application.contracts.identity import CreateUser
from application.contracts.sessions import Login, SessionIssued, SessionView
from application.identity.sessions import SessionServices, SessionUseCases
from application.identity.use_cases import IdentityUseCases
from domain.identity.ids import SessionId, UserId
from domain.identity.session import Session, SessionPolicy, TokenDigest
from domain.identity.user import User
from domain.shared.errors import DomainError
from tests.support.clock import FakeClock
from tests.support.identity import FakePasswordHasher
from tests.support.ids import SequentialIds
from tests.support.sessions import InMemoryAuthUnitOfWork, SequentialTokens

scenarios("features/sessions.feature")

POLICY = SessionPolicy(idle=timedelta(hours=12), absolute=timedelta(hours=48))


class Stores:
    def __init__(self) -> None:
        self.users: dict[UserId, User] = {}
        self.sessions: dict[SessionId, Session] = {}
        self.failures: list[tuple[str, datetime]] = []


class Outcome:
    def __init__(self) -> None:
        self.issued: SessionIssued | None = None
        self.view: SessionView | None = None
        self.errors: list[DomainError] = []
        # Токени по email у порядку видачі: сценарії звертаються до них за номером.
        self.tokens: dict[str, list[str]] = {}

    def run[T](
        self, portal: BlockingPortal, action: Callable[[], Awaitable[T]]
    ) -> T | None:
        try:
            return portal.call(action)
        except DomainError as error:
            self.errors.append(error)
            return None


@pytest.fixture
def stores() -> Stores:
    return Stores()


@pytest.fixture
def identity(stores: Stores, clock: FakeClock, ids: SequentialIds) -> IdentityUseCases:
    return IdentityUseCases(
        lambda: InMemoryAuthUnitOfWork(stores.users, stores.sessions, stores.failures),
        clock,
        ids,
        FakePasswordHasher(),
    )


@pytest.fixture
def sessions(
    stores: Stores, identity: IdentityUseCases, clock: FakeClock, ids: SequentialIds
) -> SessionUseCases:
    return SessionUseCases(
        lambda: InMemoryAuthUnitOfWork(stores.users, stores.sessions, stores.failures),
        identity,
        SessionServices(clock=clock, ids=ids, tokens=SequentialTokens(), policy=POLICY),
    )


@pytest.fixture
def outcome() -> Outcome:
    return Outcome()


@given(parsers.parse('є користувач "{email}" з іменем "{name}" і паролем "{password}"'))
def existing_user(
    portal: BlockingPortal,
    identity: IdentityUseCases,
    email: str,
    name: str,
    password: str,
) -> None:
    command = CreateUser(email=email, display_name=name, password=password)
    portal.call(identity.create_user, command)


def _login(
    portal: BlockingPortal,
    sessions: SessionUseCases,
    outcome: Outcome,
    email: str,
    password: str,
    client: str,
) -> SessionIssued | None:
    command = Login(email=email, password=password, client=client)
    return outcome.run(portal, lambda: sessions.login(command))


@when(
    parsers.parse(
        'я входжу з email "{email}" і паролем "{password}" з клієнта "{client}"'
    )
)
def log_in(
    portal: BlockingPortal,
    sessions: SessionUseCases,
    outcome: Outcome,
    email: str,
    password: str,
    client: str,
) -> None:
    issued = _login(portal, sessions, outcome, email, password, client)
    if issued is not None:
        outcome.issued = issued
        outcome.tokens.setdefault(issued.user.email, []).append(issued.token)


@when(
    parsers.parse(
        'я {count:d} разів входжу з email "{email}" і хибним паролем з клієнта "{client}"'
    )
)
def fail_to_log_in(
    portal: BlockingPortal,
    sessions: SessionUseCases,
    outcome: Outcome,
    count: int,
    email: str,
    client: str,
) -> None:
    for _ in range(count):
        _login(portal, sessions, outcome, email, "wrong password 123", client)
    outcome.errors.clear()  # перевіряється лише фінальний вхід


@when(parsers.parse("минає {hours:d} годин"))
def hours_pass(clock: FakeClock, hours: int) -> None:
    clock.advance(timedelta(hours=hours))


@when(parsers.parse("минає {minutes:d} хвилин"))
def minutes_pass(clock: FakeClock, minutes: int) -> None:
    clock.advance(timedelta(minutes=minutes))


def _identify(
    portal: BlockingPortal, sessions: SessionUseCases, outcome: Outcome, token: str
) -> None:
    outcome.view = outcome.run(portal, lambda: sessions.identify(token))


@when(parsers.parse('я перевіряю сесію користувача "{email}"'))
def identify_latest(
    portal: BlockingPortal, sessions: SessionUseCases, outcome: Outcome, email: str
) -> None:
    outcome.errors.clear()
    _identify(portal, sessions, outcome, outcome.tokens[email][-1])


@when(parsers.parse('я перевіряю сесію номер {number:d} користувача "{email}"'))
def identify_numbered(
    portal: BlockingPortal,
    sessions: SessionUseCases,
    outcome: Outcome,
    number: int,
    email: str,
) -> None:
    outcome.errors.clear()
    _identify(portal, sessions, outcome, outcome.tokens[email][number - 1])


@when(parsers.parse('я перевіряю сесію з токеном "{token}"'))
def identify_token(
    portal: BlockingPortal, sessions: SessionUseCases, outcome: Outcome, token: str
) -> None:
    _identify(portal, sessions, outcome, token)


@when("я перевіряю сесію з порожнім токеном")
def identify_empty_token(
    portal: BlockingPortal, sessions: SessionUseCases, outcome: Outcome
) -> None:
    _identify(portal, sessions, outcome, "")


@when(parsers.parse("я перевіряю сесію з токеном довжиною {length:d} символів"))
def identify_long_token(
    portal: BlockingPortal, sessions: SessionUseCases, outcome: Outcome, length: int
) -> None:
    outcome.errors.clear()
    _identify(portal, sessions, outcome, "t" * length)


def _logout(
    portal: BlockingPortal, sessions: SessionUseCases, outcome: Outcome, token: str
) -> None:
    outcome.run(portal, lambda: sessions.logout(token))


@when(parsers.parse('я закриваю сесію користувача "{email}"'))
def logout_latest(
    portal: BlockingPortal, sessions: SessionUseCases, outcome: Outcome, email: str
) -> None:
    _logout(portal, sessions, outcome, outcome.tokens[email][-1])


@when(parsers.parse('я закриваю сесію номер {number:d} користувача "{email}"'))
def logout_numbered(
    portal: BlockingPortal,
    sessions: SessionUseCases,
    outcome: Outcome,
    number: int,
    email: str,
) -> None:
    _logout(portal, sessions, outcome, outcome.tokens[email][number - 1])


@when(parsers.parse('я закриваю сесію з токеном "{token}"'))
def logout_token(
    portal: BlockingPortal, sessions: SessionUseCases, outcome: Outcome, token: str
) -> None:
    _logout(portal, sessions, outcome, token)


@then(parsers.parse('сесію видано для "{email}"'))
def session_issued(outcome: Outcome, email: str) -> None:
    assert outcome.errors == []
    assert outcome.issued is not None
    assert outcome.issued.user.email == email
    assert outcome.issued.token


@then(parsers.parse('сесія належить "{email}"'))
def session_belongs(outcome: Outcome, email: str) -> None:
    assert outcome.errors == []
    assert outcome.view is not None
    assert outcome.view.user.email == email


@then(parsers.parse('імʼя в сесії — "{name}"'))
def session_name(outcome: Outcome, name: str) -> None:
    assert outcome.view is not None
    assert outcome.view.user.display_name == name


@then(parsers.parse('у сховищі сесій немає токена користувача "{email}"'))
def only_digest_stored(stores: Stores, outcome: Outcome, email: str) -> None:
    token = outcome.tokens[email][-1]
    (session,) = stores.sessions.values()
    assert session.token_digest == TokenDigest.from_token(token)
    assert token not in repr(session)
    assert token not in session.token_digest.value


@then(parsers.parse("кількість сесій у сховищі — {count:d}"))
def session_count(stores: Stores, count: int) -> None:
    assert len(stores.sessions) == count


@then(parsers.parse("кількість записів про невдалі входи — {count:d}"))
def failure_count(stores: Stores, count: int) -> None:
    assert len(stores.failures) == count


@then(parsers.parse('отримую помилку "{code}"'))
def error_with_code(outcome: Outcome, code: str) -> None:
    assert outcome.errors, "помилки не було"
    assert outcome.errors[-1].code == code


@then("помилок не було")
def no_errors(outcome: Outcome) -> None:
    assert outcome.errors == []


@then(parsers.parse("повторна спроба можлива через {seconds:d} секунд"))
def retry_after(outcome: Outcome, seconds: int) -> None:
    error = outcome.errors[-1]
    assert getattr(error, "retry_after", None) == seconds
