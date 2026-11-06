"""Помилки identity: стабільні коди; EmailTaken — конфлікт (HTTP 409 дає мапер категорій)."""

from domain.identity.errors import (
    AltchaFailed,
    CodeIncorrect,
    EmailTaken,
    InvalidCredentials,
    InviteAlreadyUsed,
    PasswordWeak,
    SignupExpired,
    SignupMailUnavailable,
)
from domain.shared.errors import Conflict, DomainError, InvalidValue, NotFound


def test_codes_are_stable() -> None:
    assert InvalidCredentials.code == "invalid_credentials"
    assert EmailTaken.code == "email_taken"


def test_email_taken_is_a_conflict() -> None:
    assert issubclass(EmailTaken, Conflict)


def test_invalid_credentials_is_a_plain_domain_error() -> None:
    # Не NotFound і не InvalidValue: відповідь не розкриває, що саме не так з входом.
    assert issubclass(InvalidCredentials, DomainError)
    assert not issubclass(InvalidCredentials, NotFound | InvalidValue)


def test_signup_error_codes_are_stable() -> None:
    assert AltchaFailed.code == "challenge_failed"
    assert PasswordWeak.code == "password_weak"
    assert SignupExpired.code == "signup_expired"
    assert CodeIncorrect.code == "code_incorrect"
    assert InviteAlreadyUsed.code == "invite_used"
    assert SignupMailUnavailable.code == "mail_unavailable"


def test_signup_errors_have_the_category_that_decides_their_http_status() -> None:
    assert issubclass(PasswordWeak, InvalidValue)
    assert issubclass(SignupExpired, InvalidValue)
    assert issubclass(CodeIncorrect, InvalidValue)
    assert issubclass(InviteAlreadyUsed, Conflict)


def test_a_wrong_code_tells_how_many_attempts_are_left() -> None:
    assert CodeIncorrect("Невірний код", attempts_left=3).attempts_left == 3
