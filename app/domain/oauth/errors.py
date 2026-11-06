"""Помилки OAuth: код збігається з кодом помилки протоколу (RFC 6749, 7591, 8707)."""

from domain.shared.errors import DomainError


class InvalidRedirectUri(DomainError):
    code = "invalid_redirect_uri"


class InvalidTarget(DomainError):
    code = "invalid_target"


class InvalidGrant(DomainError):
    """Код чи токен невідомий, прострочений, чужий, уже використаний або грант відкликано."""

    code = "invalid_grant"


class AuthorizationExpired(DomainError):
    """Запит на авторизацію (rid) невідомий або застарів: підключення треба почати знову."""

    code = "authorization_expired"
