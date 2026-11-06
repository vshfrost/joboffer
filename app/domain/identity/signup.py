"""Режим реєстрації: закрита (за замовчуванням) або за одноразовим запрошенням."""

from enum import StrEnum


class SignupMode(StrEnum):
    CLOSED = "closed"
    INVITE = "invite"
