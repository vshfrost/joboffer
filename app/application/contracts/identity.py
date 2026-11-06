"""Команди й результати контексту identity: примітиви, а не value objects (їх будує use case).

Пароль — лише тут і лише в команді: у repr його немає, у результатах — теж.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateUser:
    email: str
    display_name: str
    password: str = field(repr=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class Authenticate:
    email: str
    password: str = field(repr=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class UserView:
    id: str
    email: str
    display_name: str
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class GoogleClaims:
    """Перевірені Authlib claims `id_token` Google: що саме потрібно для входу."""

    subject: str
    email: str | None
    email_verified: bool
    name: str | None
