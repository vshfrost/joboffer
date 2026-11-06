"""Сутності OAuth: клієнт (DCR), грант користувача клієнту, код і токени (лише дайджести)."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Self

from domain.identity.ids import GrantId, UserId
from domain.identity.session import TokenDigest
from domain.oauth.ids import ClientId
from domain.shared.errors import InvalidValue


@dataclass(frozen=True, slots=True, kw_only=True)
class OAuthClient:
    """`metadata` — документ реєстрації (RFC 7591) без секретів: усі DCR-клієнти публічні."""

    id: ClientId
    name: str | None
    redirect_uris: tuple[str, ...]
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True, kw_only=True)
class Grant:
    """Дозвіл користувача клієнту. Відкликання знищує дію всіх токенів гранту."""

    id: GrantId
    user_id: UserId
    client_id: ClientId
    resource: str
    created_at: datetime
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def revoke(self, at: datetime) -> Self:
        return replace(self, revoked_at=at)


class TokenKind(StrEnum):
    CODE = "code"
    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True, slots=True, kw_only=True)
class CodeBinding:
    """Що клієнт заявив на /authorize: потрібне, щоб звірити /token (PKCE, redirect_uri)."""

    code_challenge: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredToken:
    """Код або токен у сховищі: лише sha256-дайджест секрету. `consumed_at` — використано (код, refresh)."""

    digest: TokenDigest
    kind: TokenKind
    grant_id: GrantId
    expires_at: datetime
    consumed_at: datetime | None = None
    code: CodeBinding | None = None

    @property
    def binding(self) -> CodeBinding:
        """Привʼязка коду; у токена без неї — `InvalidValue`."""
        if self.code is None:
            raise InvalidValue("code", "Токен не має привʼязки коду авторизації")
        return self.code

    def is_expired(self, now: datetime) -> bool:
        """Межа виключна: рівно в момент `expires_at` токен уже прострочений."""
        return now >= self.expires_at


@dataclass(frozen=True, slots=True, kw_only=True)
class PendingAuthorization:
    """Запит із /authorize, що чекає входу користувача. Живе в памʼяті процесу."""

    client_id: ClientId
    binding: CodeBinding
    state: str | None
    expires_at: datetime
