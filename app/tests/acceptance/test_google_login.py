"""Кроки для features/google_login.feature: use cases сесій + in-memory адаптери через портал."""

from datetime import datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given, parsers, scenarios, then, when

from application.contracts.identity import CreateUser, GoogleClaims
from application.contracts.sessions import SessionIssued
from application.identity.sessions import SessionServices, SessionUseCases
from application.identity.use_cases import IdentityUseCases
from domain.identity.external_identity import ExternalIdentity
from domain.identity.ids import SessionId, UserId
from domain.identity.session import Session, SessionPolicy
from domain.identity.user import User
from domain.shared.errors import DomainError
from tests.support.clock import FakeClock
from tests.support.identity import FakePasswordHasher
from tests.support.ids import SequentialIds
from tests.support.sessions import InMemoryAuthUnitOfWork, SequentialTokens

scenarios("features/google_login.feature")

POLICY = SessionPolicy(idle=timedelta(hours=12), absolute=timedelta(hours=48))


class Stores:
    def __init__(self) -> None:
        self.users: dict[UserId, User] = {}
        self.sessions: dict[SessionId, Session] = {}
        self.failures: list[tuple[str, datetime]] = []
        self.identities: dict[tuple[str, str], ExternalIdentity] = {}


class Outcome:
    def __init__(self) -> None:
        self.issued: SessionIssued | None = None
        self.errors: list[DomainError] = []


@pytest.fixture
def stores() -> Stores:
    return Stores()


@pytest.fixture
def outcome() -> Outcome:
    return Outcome()


def _uow(stores: Stores) -> InMemoryAuthUnitOfWork:
    return InMemoryAuthUnitOfWork(
        stores.users, stores.sessions, stores.failures, stores.identities
    )


@pytest.fixture
def identity(stores: Stores, clock: FakeClock, ids: SequentialIds) -> IdentityUseCases:
    return IdentityUseCases(lambda: _uow(stores), clock, ids, FakePasswordHasher())


@pytest.fixture
def sessions(
    stores: Stores, identity: IdentityUseCases, clock: FakeClock, ids: SequentialIds
) -> SessionUseCases:
    return SessionUseCases(
        lambda: _uow(stores),
        identity,
        SessionServices(clock=clock, ids=ids, tokens=SequentialTokens(), policy=POLICY),
    )


@given(parsers.parse('є користувач "{email}" з іменем "{name}" і паролем "{password}"'))
def existing_user(
    portal: BlockingPortal,
    identity: IdentityUseCases,
    email: str,
    name: str,
    password: str,
) -> None:
    portal.call(
        identity.create_user,
        CreateUser(email=email, display_name=name, password=password),
    )


def _google(
    portal: BlockingPortal,
    sessions: SessionUseCases,
    outcome: Outcome,
    claims: GoogleClaims,
) -> None:
    outcome.errors.clear()
    outcome.issued = None
    try:
        outcome.issued = portal.call(sessions.sign_in_with_google, claims)
    except DomainError as error:
        outcome.errors.append(error)


@given(
    parsers.parse('я входжу через Google з sub "{sub}" і підтвердженим email "{email}"')
)
@when(
    parsers.parse('я входжу через Google з sub "{sub}" і підтвердженим email "{email}"')
)
def google_verified(
    portal: BlockingPortal,
    sessions: SessionUseCases,
    outcome: Outcome,
    sub: str,
    email: str,
) -> None:
    claims = GoogleClaims(subject=sub, email=email, email_verified=True, name="Google")
    _google(portal, sessions, outcome, claims)


@when(
    parsers.parse(
        'я входжу через Google з sub "{sub}" і непідтвердженим email "{email}"'
    )
)
def google_unverified(
    portal: BlockingPortal,
    sessions: SessionUseCases,
    outcome: Outcome,
    sub: str,
    email: str,
) -> None:
    claims = GoogleClaims(subject=sub, email=email, email_verified=False, name=None)
    _google(portal, sessions, outcome, claims)


@when(parsers.parse('я входжу через Google з sub "{sub}" без email'))
def google_no_email(
    portal: BlockingPortal, sessions: SessionUseCases, outcome: Outcome, sub: str
) -> None:
    claims = GoogleClaims(subject=sub, email=None, email_verified=True, name=None)
    _google(portal, sessions, outcome, claims)


@then(parsers.parse('сесію видано для "{email}"'))
def session_issued(outcome: Outcome, email: str) -> None:
    assert outcome.errors == []
    assert outcome.issued is not None
    assert outcome.issued.user.email == email


@then(parsers.parse('отримую помилку "{code}"'))
def error_with_code(outcome: Outcome, code: str) -> None:
    assert outcome.errors, "помилки не було"
    assert outcome.errors[-1].code == code


@then(parsers.parse("кількість сесій у сховищі — {count:d}"))
def session_count(stores: Stores, count: int) -> None:
    assert len(stores.sessions) == count


@then(parsers.parse("кількість користувачів у сховищі — {count:d}"))
def user_count(stores: Stores, count: int) -> None:
    assert len(stores.users) == count
