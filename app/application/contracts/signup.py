"""Команди й результати реєстрації: примітиви; пароль, токен запрошення й код не потрапляють у repr."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True, kw_only=True)
class Signup:
    email: str
    password: str = field(repr=False)
    # Порожнє імʼя — частина email до `@`.
    display_name: str = ""
    invite: str = field(repr=False)
    # Версія умов, з якою погодився користувач; порожня — згоди нема.
    terms_version: str = ""
    # Розв'язок ALTCHA (base64-JSON віджета).
    altcha: str = field(repr=False)
    # Приманка для ботів: людина її не бачить і не заповнює.
    website: str = ""
    # Непрозора мітка клієнта (IP, який визначив транспорт) — лише для лімітів.
    client: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SignupAccepted:
    signup_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifySignup:
    signup_id: str
    code: str = field(repr=False)
