"""Кроки для features/identity.feature: use cases + in-memory адаптери через портал."""

from collections.abc import Awaitable, Callable

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given, parsers, scenarios, then, when

from application.contracts.identity import Authenticate, CreateUser, UserView
from application.identity.use_cases import IdentityUseCases
from domain.identity.ids import UserId
from domain.identity.user import User
from domain.shared.errors import DomainError, InvalidValue
from tests.support.clock import FakeClock
from tests.support.identity import FakePasswordHasher, InMemoryIdentityUnitOfWork
from tests.support.ids import SequentialIds

scenarios("features/identity.feature")


class Outcome:
    def __init__(self) -> None:
        self.user: UserView | None = None
        self.errors: list[DomainError] = []

    def run(
        self, portal: BlockingPortal, action: Callable[[], Awaitable[UserView]]
    ) -> None:
        try:
            self.user = portal.call(action)
        except DomainError as error:
            self.errors.append(error)


@pytest.fixture
def store() -> dict[UserId, User]:
    return {}


@pytest.fixture
def identity(
    store: dict[UserId, User], clock: FakeClock, ids: SequentialIds
) -> IdentityUseCases:
    return IdentityUseCases(
        lambda: InMemoryIdentityUnitOfWork(store),
        clock,
        ids,
        FakePasswordHasher(),
    )


@pytest.fixture
def outcome() -> Outcome:
    return Outcome()


@pytest.fixture
def registered() -> dict[str, UserView]:
    return {}


@given(parsers.parse('є користувач "{email}" з іменем "{name}" і паролем "{password}"'))
def existing_user(
    portal: BlockingPortal,
    identity: IdentityUseCases,
    registered: dict[str, UserView],
    email: str,
    name: str,
    password: str,
) -> None:
    command = CreateUser(email=email, display_name=name, password=password)
    registered[email] = portal.call(identity.create_user, command)


@when(
    parsers.parse(
        'я створюю користувача "{email}" з іменем "{name}" і паролем "{password}"'
    )
)
def create_user(
    portal: BlockingPortal,
    identity: IdentityUseCases,
    outcome: Outcome,
    email: str,
    name: str,
    password: str,
) -> None:
    command = CreateUser(email=email, display_name=name, password=password)
    outcome.run(portal, lambda: identity.create_user(command))


@when(
    parsers.parse(
        'я створюю користувача "{email}" з іменем "{name}" і паролем із {length:d} символів'
    )
)
def create_user_with_length(
    portal: BlockingPortal,
    identity: IdentityUseCases,
    outcome: Outcome,
    email: str,
    name: str,
    length: int,
) -> None:
    command = CreateUser(email=email, display_name=name, password="x" * length)
    outcome.run(portal, lambda: identity.create_user(command))


@when(parsers.parse('я входжу з email "{email}" і паролем "{password}"'))
def log_in(
    portal: BlockingPortal,
    identity: IdentityUseCases,
    outcome: Outcome,
    email: str,
    password: str,
) -> None:
    command = Authenticate(email=email, password=password)
    outcome.run(portal, lambda: identity.authenticate(command))


@when(parsers.parse('я входжу з email "{email}" і паролем із {length:d} символів'))
def log_in_with_length(
    portal: BlockingPortal,
    identity: IdentityUseCases,
    outcome: Outcome,
    email: str,
    length: int,
) -> None:
    command = Authenticate(email=email, password="x" * length)
    outcome.run(portal, lambda: identity.authenticate(command))


@then(parsers.parse('користувач створений з email "{email}" і іменем "{name}"'))
def user_created(outcome: Outcome, email: str, name: str) -> None:
    assert outcome.errors == []
    assert outcome.user is not None
    assert (outcome.user.email, outcome.user.display_name) == (email, name)


@then(parsers.parse('вхід успішний для "{email}"'))
def logged_in(outcome: Outcome, email: str) -> None:
    assert outcome.errors == []
    assert outcome.user is not None
    assert outcome.user.email == email


@then(parsers.parse('вхід належить користувачу з іменем "{name}"'))
def logged_in_as(outcome: Outcome, name: str) -> None:
    assert outcome.user is not None
    assert outcome.user.display_name == name


@then(parsers.parse('користувачі "{first}" і "{second}" мають різні id'))
def different_ids(registered: dict[str, UserView], first: str, second: str) -> None:
    assert registered[first].id != registered[second].id


@then(
    parsers.parse('у сховищі хеш пароля користувача "{email}" не містить "{password}"')
)
def hash_has_no_password(store: dict[UserId, User], email: str, password: str) -> None:
    (user,) = [user for user in store.values() if user.email.value == email]
    assert user.password_hash is not None
    assert user.password_hash.value
    assert password not in user.password_hash.value


@then(parsers.parse('отримую помилку "{code}" для поля "{field}"'))
def error_for_field(outcome: Outcome, code: str, field: str) -> None:
    (error,) = outcome.errors
    assert isinstance(error, InvalidValue)
    assert (error.code, error.field) == (code, field)


@then(parsers.parse('отримую помилку "{code}"'))
def error_with_code(outcome: Outcome, code: str) -> None:
    (error,) = outcome.errors
    assert error.code == code


@then(parsers.parse('обидві спроби дають помилку "{code}" з однаковим текстом'))
def same_error_twice(outcome: Outcome, code: str) -> None:
    first, second = outcome.errors
    assert (first.code, second.code) == (code, code)
    assert first.message == second.message
