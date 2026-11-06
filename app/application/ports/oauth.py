"""Порти OAuth: клієнти, гранти, токени, запити в очікуванні входу."""

from datetime import datetime
from typing import Protocol

from application.ports.agents import AgentRegistry
from application.ports.unit_of_work import UnitOfWork
from domain.identity.ids import GrantId, UserId
from domain.identity.session import TokenDigest
from domain.oauth.entities import (
    Grant,
    OAuthClient,
    PendingAuthorization,
    StoredToken,
)
from domain.oauth.ids import ClientId


class OAuthClients(Protocol):
    async def add(self, client: OAuthClient, at: datetime | None = None) -> None:
        """`at` — коли клієнта зареєстровано; без нього час ставить база."""
        ...

    async def get(self, client_id: ClientId) -> OAuthClient | None: ...

    async def delete_unused(self, registered_before: datetime) -> None:
        """Прибирає клієнтів, зареєстрованих раніше за `registered_before`, що так і не отримали жодного гранту."""
        ...


class Grants(Protocol):
    async def add(self, grant: Grant) -> None: ...

    async def get(self, grant_id: GrantId) -> Grant | None: ...

    async def revoke(self, grant_id: GrantId, at: datetime) -> None:
        """Нема такого чи вже відкликано — нічого не робить."""
        ...

    async def has_live(self, user_id: UserId, now: datetime) -> bool:
        """Чи має користувач грант, що ще діє: не відкликаний, з чинним (не використаним і не простроченим) refresh-токеном."""
        ...

    async def delete_without_tokens(self) -> None:
        """Прибирає гранти, чиї коди й токени вже видалено (код так і не обміняли)."""
        ...


class OAuthTokens(Protocol):
    async def add(self, token: StoredToken) -> None: ...

    async def find_by_digest(self, digest: TokenDigest) -> StoredToken | None: ...

    async def consume(self, digest: TokenDigest, at: datetime) -> bool:
        """Атомарно позначає використаним. `False` — уже використано або нема: це повторне пред'явлення."""
        ...

    async def delete_expired(self, now: datetime) -> None: ...


class OAuthUnitOfWork(UnitOfWork, Protocol):
    @property
    def oauth_clients(self) -> OAuthClients: ...

    @property
    def grants(self) -> Grants: ...

    @property
    def oauth_tokens(self) -> OAuthTokens: ...

    @property
    def user_agents(self) -> AgentRegistry: ...


class PendingAuthorizations(Protocol):
    """Запити між /authorize і входом: лише в памʼяті процесу, живуть хвилини."""

    def put(self, rid: str, pending: PendingAuthorization) -> None:
        """Переповнений — витісняє найстаріші."""
        ...

    def get(self, rid: str) -> PendingAuthorization | None: ...

    def take(self, rid: str) -> PendingAuthorization | None:
        """Забирає запит: другий виклик із тим самим rid дає `None`."""
        ...
