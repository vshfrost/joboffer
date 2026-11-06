"""Команди й результати запрошень на реєстрацію: примітиви; токен не потрапляє в repr."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckInvite:
    token: str = field(repr=False)
    # Непрозора мітка клієнта (IP, який визначив транспорт) — лише для ліміту перевірок.
    client: str


@dataclass(frozen=True, slots=True, kw_only=True)
class InviteStatus:
    valid: bool
    expires_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class InviteIssued:
    token: str = field(repr=False)
    expires_at: datetime
