"""In-memory адаптери OAuth для core-тестів: та сама семантика, що в Postgres (commit, атомарний consume)."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from types import TracebackType
from typing import Self

from domain.agents.agent import UserAgent
from domain.identity.ids import GrantId, UserId
from domain.identity.session import TokenDigest
from domain.oauth.entities import (
    Grant,
    OAuthClient,
    PendingAuthorization,
    StoredToken,
    TokenKind,
)
from domain.oauth.ids import ClientId


@dataclass(slots=True)
class OAuthStore:
    clients: dict[ClientId, OAuthClient] = field(default_factory=dict)
    grants: dict[GrantId, Grant] = field(default_factory=dict)
    tokens: dict[TokenDigest, StoredToken] = field(default_factory=dict)
    agents: dict[tuple[UserId, ClientId], UserAgent] = field(default_factory=dict)
    # Тест «гонки»: конкурентна транзакція встигла спалити токен між перевіркою й consume.
    lose_consume_race: bool = False

    def copy(self) -> OAuthStore:
        return OAuthStore(
            dict(self.clients),
            dict(self.grants),
            dict(self.tokens),
            dict(self.agents),
            self.lose_consume_race,
        )


class InMemoryOAuthClients:
    def __init__(self, rows: dict[ClientId, OAuthClient]) -> None:
        self._rows = rows

    async def add(self, client: OAuthClient) -> None:
        self._rows[client.id] = client

    async def get(self, client_id: ClientId) -> OAuthClient | None:
        return self._rows.get(client_id)


class InMemoryGrants:
    def __init__(self, store: OAuthStore) -> None:
        self._store = store

    async def add(self, grant: Grant) -> None:
        self._store.grants[grant.id] = grant

    async def get(self, grant_id: GrantId) -> Grant | None:
        return self._store.grants.get(grant_id)

    async def revoke(self, grant_id: GrantId, at: datetime) -> None:
        grant = self._store.grants.get(grant_id)
        if grant is not None and grant.is_active:
            self._store.grants[grant_id] = grant.revoke(at)

    async def has_live(self, user_id: UserId, now: datetime) -> bool:
        return any(
            token.kind is TokenKind.REFRESH
            and token.consumed_at is None
            and not token.is_expired(now)
            and (grant := self._store.grants.get(token.grant_id)) is not None
            and grant.user_id == user_id
            and grant.is_active
            for token in self._store.tokens.values()
        )

    async def delete_without_tokens(self) -> None:
        with_tokens = {token.grant_id for token in self._store.tokens.values()}
        for grant_id in list(self._store.grants):
            if grant_id not in with_tokens:
                del self._store.grants[grant_id]


class InMemoryUserAgents:
    def __init__(self, rows: dict[tuple[UserId, ClientId], UserAgent]) -> None:
        self._rows = rows

    async def upsert(self, agent: UserAgent) -> None:
        known = self._rows.get((agent.user_id, agent.client_id))
        self._rows[(agent.user_id, agent.client_id)] = (
            agent if known is None else replace(known, grant_id=agent.grant_id)
        )


class InMemoryOAuthTokens:
    def __init__(self, store: OAuthStore) -> None:
        self._store = store
        self._rows = store.tokens

    async def add(self, token: StoredToken) -> None:
        self._rows[token.digest] = token

    async def find_by_digest(self, digest: TokenDigest) -> StoredToken | None:
        return self._rows.get(digest)

    async def consume(self, digest: TokenDigest, at: datetime) -> bool:
        token = self._rows.get(digest)
        if (
            self._store.lose_consume_race
            or token is None
            or token.consumed_at is not None
        ):
            return False
        self._rows[digest] = replace(token, consumed_at=at)
        return True

    async def delete_expired(self, now: datetime) -> None:
        for digest, token in list(self._rows.items()):
            if token.is_expired(now):
                del self._rows[digest]


class InMemoryOAuthUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(self, store: OAuthStore) -> None:
        self._store = store
        self._staged: OAuthStore | None = None

    def _open(self) -> OAuthStore:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged

    @property
    def oauth_clients(self) -> InMemoryOAuthClients:
        return InMemoryOAuthClients(self._open().clients)

    @property
    def grants(self) -> InMemoryGrants:
        return InMemoryGrants(self._open())

    @property
    def oauth_tokens(self) -> InMemoryOAuthTokens:
        return InMemoryOAuthTokens(self._open())

    @property
    def user_agents(self) -> InMemoryUserAgents:
        return InMemoryUserAgents(self._open().agents)

    async def __aenter__(self) -> Self:
        self._staged = self._store.copy()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        staged = self._open()
        self._store.clients = staged.clients
        self._store.grants = staged.grants
        self._store.tokens = staged.tokens
        self._store.agents = staged.agents


class InMemoryPending:
    """Підміна порту `PendingAuthorizations` для core-тестів (без обмеження розміру)."""

    def __init__(self) -> None:
        self._items: dict[str, PendingAuthorization] = {}

    def put(self, rid: str, pending: PendingAuthorization) -> None:
        self._items[rid] = pending

    def get(self, rid: str) -> PendingAuthorization | None:
        return self._items.get(rid)

    def take(self, rid: str) -> PendingAuthorization | None:
        return self._items.pop(rid, None)
