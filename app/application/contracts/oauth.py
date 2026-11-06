"""Команди й результати OAuth: примітиви. Коди й токени — лише в результатах, у repr їх нема."""

from dataclasses import dataclass, field
from datetime import datetime

from domain.identity.ids import GrantId, UserId


@dataclass(frozen=True, slots=True, kw_only=True)
class RegisterClient:
    """`client_id` видає протокол (DCR), а не ми."""

    client_id: str
    name: str | None
    redirect_uris: tuple[str, ...]
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True, kw_only=True)
class ClientView:
    client_id: str
    name: str | None
    redirect_uris: tuple[str, ...]
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizationRequest:
    client_id: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    state: str | None
    code_challenge: str
    resource: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class PendingView:
    """Для екрана згоди: хто просить доступ і куди піде код."""

    client_name: str
    redirect_host: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizationGranted:
    redirect_uri: str
    code: str = field(repr=False)
    state: str | None
    grant_id: GrantId


@dataclass(frozen=True, slots=True, kw_only=True)
class CodeView:
    client_id: str
    code_challenge: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    expires_at: datetime
    resource: str
    user_id: UserId


@dataclass(frozen=True, slots=True, kw_only=True)
class RefreshView:
    client_id: str
    expires_at: datetime
    resource: str
    user_id: UserId


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenPair:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_in: int
    scope: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AccessView:
    """Перевірений access-токен: від імені кого й у межах якого гранту діє клієнт."""

    user_id: UserId
    grant_id: GrantId
    client_id: str
    expires_at: datetime
    resource: str
