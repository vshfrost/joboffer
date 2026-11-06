"""Сесія: дайджест токена, політика строків, ковзний простій і абсолютний строк."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from domain.identity.ids import SessionId, UserId
from domain.identity.session import Session, SessionPolicy, TokenDigest
from domain.shared.errors import InvalidValue

START = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
POLICY = SessionPolicy(idle=timedelta(hours=1), absolute=timedelta(hours=24))


def make_session() -> Session:
    return Session.start(
        id=SessionId(UUID(int=1)),
        user_id=UserId(UUID(int=2)),
        token_digest=TokenDigest.from_token("token-1"),
        now=START,
        policy=POLICY,
    )


def test_digest_is_sha256_hex_of_the_token() -> None:
    # sha256("abc") — еталонне значення з FIPS 180-2.
    assert TokenDigest.from_token("abc").value == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_different_tokens_have_different_digests() -> None:
    assert TokenDigest.from_token("a") != TokenDigest.from_token("b")


@pytest.mark.parametrize("raw", ["", "abc", "G" * 64, "A" * 64, "a" * 63])
def test_digest_must_be_64_lowercase_hex(raw: str) -> None:
    with pytest.raises(InvalidValue) as caught:
        TokenDigest(raw)
    assert caught.value.field == "token_digest"


def test_start_sets_timestamps_and_absolute_expiry() -> None:
    session = make_session()
    assert (session.created_at, session.last_seen_at) == (START, START)
    assert session.expires_at == START + timedelta(hours=24)


def test_active_until_idle_limit_exclusive() -> None:
    session = make_session()
    assert session.is_active(START + timedelta(minutes=59, seconds=59), POLICY)
    assert not session.is_active(START + timedelta(hours=1), POLICY)


def test_activity_extends_the_idle_window() -> None:
    session = make_session().seen(START + timedelta(minutes=50))
    assert session.is_active(START + timedelta(hours=1, minutes=40), POLICY)
    assert not session.is_active(START + timedelta(hours=1, minutes=50), POLICY)


def test_absolute_expiry_ends_even_an_active_session() -> None:
    session = make_session().seen(START + timedelta(hours=23, minutes=30))
    assert session.is_active(START + timedelta(hours=23, minutes=59), POLICY)
    assert not session.is_active(START + timedelta(hours=24), POLICY)


def test_seen_keeps_everything_else() -> None:
    session = make_session()
    later = session.seen(START + timedelta(minutes=5))
    assert (later.id, later.user_id, later.token_digest, later.expires_at) == (
        session.id,
        session.user_id,
        session.token_digest,
        session.expires_at,
    )


@pytest.mark.parametrize(
    ("idle", "absolute"),
    [
        (timedelta(0), timedelta(hours=1)),
        (timedelta(hours=1), timedelta(0)),
        (timedelta(hours=-1), timedelta(hours=1)),
        (timedelta(hours=2), timedelta(hours=1)),
    ],
)
def test_policy_rejects_non_positive_or_inverted_limits(
    idle: timedelta, absolute: timedelta
) -> None:
    with pytest.raises(InvalidValue) as caught:
        SessionPolicy(idle=idle, absolute=absolute)
    assert caught.value.field == "session_policy"
