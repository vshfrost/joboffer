"""Політика пароля реєстрації: від 8 символів і всі чотири класи (цифра, мала, велика, спецсимвол)."""

import pytest

from domain.identity.errors import PasswordWeak
from domain.identity.password_policy import (
    PASSWORD_MAX,
    PASSWORD_MIN,
    check_new_password,
)
from domain.shared.errors import InvalidValue


def test_limits_are_8_and_1024() -> None:
    assert PASSWORD_MIN == 8
    assert PASSWORD_MAX == 1024


def test_an_8_character_password_with_all_classes_is_accepted() -> None:
    check_new_password("Abcdef1!")


def test_a_7_character_password_is_refused_as_an_invalid_value() -> None:
    with pytest.raises(InvalidValue) as refused:
        check_new_password("Abcde1!")
    assert refused.value.field == "password"
    assert refused.value.code == "invalid_value"
    assert "8" in refused.value.message


def test_length_is_checked_before_the_classes() -> None:
    with pytest.raises(InvalidValue) as refused:
        check_new_password("abc")
    assert refused.value.code == "invalid_value"


def test_a_1024_character_password_is_accepted() -> None:
    check_new_password("Aa1!" * 256)


def test_a_1025_character_password_is_refused() -> None:
    with pytest.raises(InvalidValue) as refused:
        check_new_password("Aa1!" * 256 + "a")
    assert refused.value.code == "invalid_value"


@pytest.mark.parametrize(
    "password",
    [
        "Correct-Horse-Bat",
        "CORRECT-HORSE-9",
        "correct-horse-9",
        "CorrectHorse99",
        "Correct Horse 9",
        "12345678",
        "пароль-тест1",
    ],
)
def test_a_password_missing_a_class_is_weak(password: str) -> None:
    with pytest.raises(PasswordWeak) as refused:
        check_new_password(password)
    assert (refused.value.code, refused.value.field) == ("password_weak", "password")


def test_the_message_names_exactly_what_is_missing() -> None:
    with pytest.raises(PasswordWeak) as refused:
        check_new_password("CorrectHorse")

    message = refused.value.message
    assert "цифру" in message
    assert "спецсимвол" in message
    assert "малу літеру" not in message
    assert "велику літеру" not in message


def test_the_message_names_all_four_classes_when_nothing_matches() -> None:
    with pytest.raises(PasswordWeak) as refused:
        check_new_password("        ")

    message = refused.value.message
    for missing in ("цифру", "малу літеру", "велику літеру", "спецсимвол"):
        assert missing in message


@pytest.mark.parametrize(
    "password",
    [
        "Correct-Horse-9",
        "Пароль-тест1",
        "Correct_Horse9",
        "Correct Horse 9!",
        "Aa1~bcde",
    ],
)
def test_a_password_with_every_class_is_accepted(password: str) -> None:
    check_new_password(password)


def test_a_space_is_not_a_special_character() -> None:
    with pytest.raises(PasswordWeak):
        check_new_password("Correct Horse 9")


def test_a_common_password_that_meets_the_policy_is_accepted() -> None:
    check_new_password("Password1234!")
