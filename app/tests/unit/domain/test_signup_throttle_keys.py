"""Ключі лімітів реєстрації: окремі простори від входу й перевірки запрошень, без адрес у ключі."""

import re

from domain.identity.throttle import (
    attempt_key,
    invite_check_key,
    signup_client_key,
    signup_mail_key,
)


def test_keys_are_64_hex_characters() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", signup_client_key("10.0.0.1"))
    assert re.fullmatch(r"[0-9a-f]{64}", signup_mail_key("taras@example.com"))


def test_keys_are_stable() -> None:
    assert signup_client_key("10.0.0.1") == signup_client_key("10.0.0.1")
    assert signup_mail_key("taras@example.com") == signup_mail_key("taras@example.com")


def test_another_client_or_email_gives_another_key() -> None:
    assert signup_client_key("10.0.0.1") != signup_client_key("10.0.0.2")
    assert signup_mail_key("taras@example.com") != signup_mail_key("katya@example.com")


def test_the_email_is_normalized_before_hashing() -> None:
    assert signup_mail_key("  TARAS@Example.com ") == signup_mail_key(
        "taras@example.com"
    )


def test_the_key_spaces_do_not_overlap() -> None:
    keys = {
        signup_client_key("taras@example.com"),
        signup_mail_key("taras@example.com"),
        invite_check_key("taras@example.com"),
        attempt_key("taras@example.com", "taras@example.com"),
    }

    assert len(keys) == 4
