"""Запит на реєстрацію: код 6 цифр на 15 хвилин і 5 спроб, digest замість коду, пауза між листами."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from domain.identity.email import Email
from domain.identity.ids import SignupRequestId
from domain.identity.password import PasswordHash
from domain.identity.session import TokenDigest
from domain.identity.signup_request import (
    CODE_LENGTH,
    CODE_MAX_ATTEMPTS,
    CODE_TTL,
    MAIL_MAX_PER_WINDOW,
    MAIL_WINDOW,
    RESEND_INTERVAL,
    SIGNUP_MAX_PER_WINDOW,
    SIGNUP_WINDOW,
    SignupDraft,
    SignupRequest,
    code_digest,
)
from domain.identity.user import DisplayName

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
ID = SignupRequestId(UUID(int=7))
CODE = "483920"


def issue(code: str = CODE) -> SignupRequest:
    draft = SignupDraft(
        email=Email("taras@example.com"),
        password_hash=PasswordHash("$argon2id$secret"),
        display_name=DisplayName("Богдан"),
        invite_digest=TokenDigest.from_token("invite-token"),
        terms_version="2026-10-28",
    )
    return SignupRequest.issue(draft, id=ID, code=code, now=NOW)


def test_the_rules_are_6_digits_15_minutes_5_attempts() -> None:
    assert CODE_LENGTH == 6
    assert timedelta(minutes=15) == CODE_TTL
    assert CODE_MAX_ATTEMPTS == 5


def test_the_limits_are_60_seconds_between_mails_5_mails_and_5_signups_per_hour() -> (
    None
):
    assert timedelta(seconds=60) == RESEND_INTERVAL
    assert MAIL_MAX_PER_WINDOW == 5
    assert timedelta(hours=1) == MAIL_WINDOW
    assert SIGNUP_MAX_PER_WINDOW == 5
    assert timedelta(hours=1) == SIGNUP_WINDOW


def test_the_digest_is_sha256_of_the_request_id_and_the_code() -> None:
    assert (
        code_digest(ID, CODE)
        == hashlib.sha256(f"{ID.value}{CODE}".encode()).hexdigest()
    )


def test_the_digest_depends_on_the_request_id() -> None:
    assert code_digest(ID, CODE) != code_digest(SignupRequestId(UUID(int=8)), CODE)


def test_an_issued_request_stores_the_digest_and_not_the_code() -> None:
    request = issue()

    assert request.code_digest == code_digest(ID, CODE)
    assert CODE not in repr(request)
    assert "secret" not in repr(request)


def test_an_issued_request_starts_fresh_for_15_minutes() -> None:
    request = issue()

    assert (request.failed_attempts, request.attempts_left) == (0, 5)
    assert (request.created_at, request.sent_at) == (NOW, NOW)
    assert request.expires_at == NOW + timedelta(minutes=15)


def test_the_right_code_matches_and_a_wrong_one_does_not() -> None:
    request = issue()

    assert request.matches(CODE) is True
    assert request.matches("000000") is False


def test_a_code_with_other_length_or_non_digits_does_not_match() -> None:
    request = issue()

    assert [request.matches(c) for c in ("", "48392", "4839200", "48392a")] == [
        False
    ] * 4


def test_the_request_expires_exactly_at_15_minutes() -> None:
    request = issue()

    assert request.is_expired(NOW + timedelta(minutes=14, seconds=59)) is False
    assert request.is_expired(NOW + timedelta(minutes=15)) is True


def test_each_failed_attempt_leaves_one_less() -> None:
    request = issue().failed().failed()

    assert (request.failed_attempts, request.attempts_left) == (2, 3)


def test_the_fifth_failed_attempt_leaves_none() -> None:
    request = issue()
    for _ in range(5):
        request = request.failed()

    assert request.attempts_left == 0


def test_a_new_code_replaces_the_digest_resets_attempts_and_extends_the_term() -> None:
    later = NOW + timedelta(minutes=10)
    request = issue().failed().failed().with_new_code("111111", later)

    assert request.code_digest == code_digest(ID, "111111")
    assert request.matches("111111") is True
    assert request.matches(CODE) is False
    assert request.failed_attempts == 0
    assert request.sent_at == later
    assert request.expires_at == later + timedelta(minutes=15)
    assert request.created_at == NOW


def test_resend_waits_60_seconds_after_the_last_mail() -> None:
    request = issue()

    assert request.resend_wait(NOW + timedelta(seconds=20)) == timedelta(seconds=40)
    assert request.resend_wait(NOW + timedelta(seconds=60)) == timedelta(0)
    assert request.resend_wait(NOW + timedelta(minutes=5)) == timedelta(0)
