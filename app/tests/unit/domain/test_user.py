"""User: реєстрація, ім'я, хеш пароля не світиться в repr."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from domain.identity.email import Email
from domain.identity.events import UserRegisteredEvent
from domain.identity.ids import UserId
from domain.identity.password import PasswordHash
from domain.identity.user import DisplayName, User
from domain.shared.errors import InvalidValue

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
SECRET_HASH = "$argon2id$secret-hash-material"


def make_user() -> User:
    return User.register(
        id=UserId(UUID(int=1)),
        email=Email("taras@example.com"),
        display_name=DisplayName("Богдан"),
        password_hash=PasswordHash(SECRET_HASH),
        now=NOW,
    )


def test_register_starts_at_version_one_with_event() -> None:
    user = make_user()
    assert (user.version, user.created_at) == (1, NOW)
    assert user.events == (UserRegisteredEvent(user_id=user.id, version=1),)


def test_password_hash_is_not_in_repr() -> None:
    user = make_user()
    assert "secret-hash-material" not in repr(user)
    assert "secret-hash-material" not in repr(user.password_hash)


def test_blank_password_hash_is_rejected() -> None:
    with pytest.raises(InvalidValue) as caught:
        PasswordHash("")
    assert caught.value.field == "password_hash"


def test_user_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        make_user().__setattr__("version", 2)


def test_display_name_is_trimmed() -> None:
    assert DisplayName.parse("  Богдан  ").value == "Богдан"


@pytest.mark.parametrize("raw", ["", "   ", "x" * 101])
def test_display_name_outside_1_to_100_is_rejected(raw: str) -> None:
    with pytest.raises(InvalidValue) as caught:
        DisplayName.parse(raw)
    assert caught.value.field == "display_name"


def test_display_name_of_100_characters_is_allowed() -> None:
    assert len(DisplayName.parse("x" * 100).value) == 100


def test_display_name_constructor_does_not_trim() -> None:
    with pytest.raises(InvalidValue):
        DisplayName(" Богдан")


def test_a_new_user_has_no_terms_acceptance() -> None:
    user = make_user()

    assert (user.terms_version, user.terms_accepted_at) == (None, None)


def test_accepting_terms_records_the_version_and_the_moment() -> None:
    accepted_at = datetime(2026, 1, 1, 9, 5, tzinfo=UTC)

    user = make_user().accepting_terms("2026-10-28", accepted_at)

    assert (user.terms_version, user.terms_accepted_at) == ("2026-10-28", accepted_at)
    assert (user.id, user.email, user.version) == (make_user().id, make_user().email, 1)
