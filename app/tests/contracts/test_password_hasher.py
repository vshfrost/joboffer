"""Порт PasswordHasher: fake для core-тестів і Argon2id поводяться однаково."""

import pytest
from anyio.from_thread import BlockingPortal

from application.ports.passwords import PasswordHasher
from domain.identity.password import PasswordHash
from infrastructure.security.passwords import Argon2PasswordHasher
from tests.support.identity import FakePasswordHasher

PASSWORD = "correct horse battery"


@pytest.fixture(params=["fake", "argon2"])
def hasher(request: pytest.FixtureRequest) -> PasswordHasher:
    return FakePasswordHasher() if request.param == "fake" else Argon2PasswordHasher()


def test_correct_password_verifies(
    portal: BlockingPortal, hasher: PasswordHasher
) -> None:
    stored = portal.call(hasher.hash, PASSWORD)
    assert portal.call(hasher.verify, PASSWORD, stored) is True


def test_unicode_password_roundtrip(
    portal: BlockingPortal, hasher: PasswordHasher
) -> None:
    stored = portal.call(hasher.hash, "пароль-українською-123")
    assert portal.call(hasher.verify, "пароль-українською-123", stored) is True


def test_wrong_password_does_not_verify(
    portal: BlockingPortal, hasher: PasswordHasher
) -> None:
    stored = portal.call(hasher.hash, PASSWORD)
    assert portal.call(hasher.verify, "wrong password 123", stored) is False


def test_missing_user_never_verifies(
    portal: BlockingPortal, hasher: PasswordHasher
) -> None:
    assert portal.call(hasher.verify, PASSWORD, None) is False


def test_malformed_stored_hash_does_not_verify(
    portal: BlockingPortal, hasher: PasswordHasher
) -> None:
    assert portal.call(hasher.verify, PASSWORD, PasswordHash("not-a-hash")) is False


def test_hash_does_not_contain_the_password(
    portal: BlockingPortal, hasher: PasswordHasher
) -> None:
    assert PASSWORD not in portal.call(hasher.hash, PASSWORD).value


def test_same_password_gets_different_hashes(
    portal: BlockingPortal, hasher: PasswordHasher
) -> None:
    assert portal.call(hasher.hash, PASSWORD) != portal.call(hasher.hash, PASSWORD)
