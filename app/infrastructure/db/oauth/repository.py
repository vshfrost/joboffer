"""Клієнти, гранти й токени OAuth на Postgres."""

from datetime import datetime

from sqlalchemy import Select, delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.identity.ids import GrantId, UserId
from domain.identity.session import TokenDigest
from domain.oauth.entities import (
    CodeBinding,
    Grant,
    OAuthClient,
    StoredToken,
    TokenKind,
)
from domain.oauth.ids import ClientId
from infrastructure.db.oauth.tables import OAuthClientRow, OAuthGrantRow, OAuthTokenRow


def _client_to_domain(row: OAuthClientRow) -> OAuthClient:
    return OAuthClient(
        id=ClientId(row.id),
        name=row.name,
        redirect_uris=tuple(row.redirect_uris),
        metadata=dict(row.registration),
    )


def _grant_to_domain(row: OAuthGrantRow) -> Grant:
    return Grant(
        id=GrantId(row.id),
        user_id=UserId(row.user_id),
        client_id=ClientId(row.client_id),
        resource=row.resource,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
    )


def _token_to_domain(row: OAuthTokenRow) -> StoredToken:
    binding = None
    if row.code_challenge is not None and row.redirect_uri is not None:
        binding = CodeBinding(
            code_challenge=row.code_challenge,
            redirect_uri=row.redirect_uri,
            redirect_uri_provided_explicitly=bool(row.redirect_uri_provided_explicitly),
        )
    return StoredToken(
        digest=TokenDigest(row.digest),
        kind=TokenKind(row.kind),
        grant_id=GrantId(row.grant_id),
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
        code=binding,
    )


def live_grants(now: datetime) -> Select[OAuthGrantRow]:
    """Гранти, що ще діють: не відкликані, з чинним (не використаним і не простроченим) refresh-токеном.

    Єдине місце цього правила: `has_live` і список агентів беруть його звідси.
    """
    live_refresh = exists().where(
        OAuthTokenRow.grant_id == OAuthGrantRow.id,
        OAuthTokenRow.kind == TokenKind.REFRESH.value,
        OAuthTokenRow.consumed_at.is_(None),
        OAuthTokenRow.expires_at > now,
    )
    return select(OAuthGrantRow).where(OAuthGrantRow.revoked_at.is_(None), live_refresh)


class PostgresOAuthClients:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, client: OAuthClient) -> None:
        self._session.add(
            OAuthClientRow(
                id=client.id.value,
                name=client.name,
                redirect_uris=list(client.redirect_uris),
                registration=dict(client.metadata),
            )
        )
        await self._session.flush()

    async def get(self, client_id: ClientId) -> OAuthClient | None:
        row = await self._session.get(OAuthClientRow, client_id.value)
        return None if row is None else _client_to_domain(row)


class PostgresGrants:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, grant: Grant) -> None:
        self._session.add(
            OAuthGrantRow(
                id=grant.id.value,
                user_id=grant.user_id.value,
                client_id=grant.client_id.value,
                resource=grant.resource,
                created_at=grant.created_at,
                revoked_at=grant.revoked_at,
            )
        )
        await self._session.flush()

    async def get(self, grant_id: GrantId) -> Grant | None:
        row = await self._session.get(OAuthGrantRow, grant_id.value)
        return None if row is None else _grant_to_domain(row)

    async def revoke(self, grant_id: GrantId, at: datetime) -> None:
        await self._session.execute(
            update(OAuthGrantRow)
            .where(
                OAuthGrantRow.id == grant_id.value, OAuthGrantRow.revoked_at.is_(None)
            )
            .values(revoked_at=at)
        )

    async def has_live(self, user_id: UserId, now: datetime) -> bool:
        live = live_grants(now).where(OAuthGrantRow.user_id == user_id.value)
        return bool(await self._session.scalar(select(exists(live))))

    async def delete_without_tokens(self) -> None:
        has_tokens = exists().where(OAuthTokenRow.grant_id == OAuthGrantRow.id)
        await self._session.execute(delete(OAuthGrantRow).where(~has_tokens))


class PostgresOAuthTokens:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: StoredToken) -> None:
        binding = token.code
        self._session.add(
            OAuthTokenRow(
                digest=token.digest.value,
                grant_id=token.grant_id.value,
                kind=token.kind.value,
                expires_at=token.expires_at,
                consumed_at=token.consumed_at,
                code_challenge=None if binding is None else binding.code_challenge,
                redirect_uri=None if binding is None else binding.redirect_uri,
                redirect_uri_provided_explicitly=(
                    None
                    if binding is None
                    else binding.redirect_uri_provided_explicitly
                ),
            )
        )
        await self._session.flush()

    async def find_by_digest(self, digest: TokenDigest) -> StoredToken | None:
        row = await self._session.get(OAuthTokenRow, digest.value)
        return None if row is None else _token_to_domain(row)

    async def consume(self, digest: TokenDigest, at: datetime) -> bool:
        consumed = await self._session.scalar(
            update(OAuthTokenRow)
            .where(
                OAuthTokenRow.digest == digest.value,
                OAuthTokenRow.consumed_at.is_(None),
            )
            .values(consumed_at=at)
            .returning(OAuthTokenRow.digest)
        )
        return consumed is not None

    async def delete_expired(self, now: datetime) -> None:
        await self._session.execute(
            delete(OAuthTokenRow).where(OAuthTokenRow.expires_at <= now)
        )
