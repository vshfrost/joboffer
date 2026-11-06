"""Команди й результати сесій: примітиви; токен і пароль не потрапляють у repr."""

from dataclasses import dataclass, field
from datetime import datetime

from application.contracts.identity import UserView


@dataclass(frozen=True, slots=True, kw_only=True)
class Login:
    email: str
    password: str = field(repr=False)
    # Непрозора мітка клієнта (IP, який визначив транспорт) — лише для ліміту спроб.
    client: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionIssued:
    token: str = field(repr=False)
    user: UserView
    expires_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionView:
    session_id: str
    user: UserView
    expires_at: datetime
