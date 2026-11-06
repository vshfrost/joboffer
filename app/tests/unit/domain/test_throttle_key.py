"""Ключ ліміту спроб входу: клієнт + нормалізований email, без самих значень у ключі."""

import re

import pytest

from domain.identity.throttle import attempt_key


def test_key_is_64_hex_characters() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", attempt_key("10.0.0.1", "taras@example.com"))


def test_key_is_stable() -> None:
    assert attempt_key("10.0.0.1", "taras@example.com") == attempt_key(
        "10.0.0.1", "taras@example.com"
    )


def test_email_is_normalized_before_hashing() -> None:
    assert attempt_key("10.0.0.1", "  TARAS@Example.com ") == attempt_key(
        "10.0.0.1", "taras@example.com"
    )


@pytest.mark.parametrize(
    ("client", "email"),
    [("10.0.0.2", "taras@example.com"), ("10.0.0.1", "katya@example.com")],
)
def test_other_client_or_email_gives_another_key(client: str, email: str) -> None:
    assert attempt_key(client, email) != attempt_key("10.0.0.1", "taras@example.com")


def test_key_does_not_leak_inputs() -> None:
    key = attempt_key("10.0.0.1", "taras@example.com")
    assert "10.0.0.1" not in key
    assert "taras" not in key


def test_client_and_email_cannot_be_shifted_into_each_other() -> None:
    assert attempt_key("a|b", "c") != attempt_key("a", "b|c")


@pytest.mark.parametrize("email", ["", "not-an-email", "x" * 5000])
def test_malformed_email_still_gets_a_key(email: str) -> None:
    assert len(attempt_key("10.0.0.1", email)) == 64
