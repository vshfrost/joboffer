"""Репозиторії OAuth на справжній базі: та сама семантика, що в in-memory, і лише дайджести секретів."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.identity.email import Email
from domain.identity.ids import GrantId, UserId
from domain.identity.password import PasswordHash
from domain.identity.session import TokenDigest
from domain.identity.user import DisplayName, User
from domain.oauth.entities import (
    CodeBinding,
    Grant,
    OAuthClient,
    StoredToken,
    TokenKind,
)
from domain.oauth.ids import ClientId
from infrastructure.db.unit_of_work import UnitOfWorkFactory, unit_of_work_factory

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
USER = UserId(UUID(int=1))
CLIENT = ClientId(UUID(int=10))
RESOURCE = "https://agent.example/joboffer"
BINDING = CodeBinding(
    code_challenge="challenge-abc",
    redirect_uri="https://claude.ai/api/mcp/auth_callback",
    redirect_uri_provided_explicitly=True,
)


@pytest.fixture
def uow(portal: BlockingPortal, engine: AsyncEngine) -> UnitOfWorkFactory:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
            await conn.execute(text("TRUNCATE oauth_clients CASCADE"))

    portal.call(clean)
    factory = unit_of_work_factory(engine)

    async def seed() -> None:
        async with factory() as tx:
            await tx.users.add(
                User.register(
                    id=USER,
                    email=Email("taras@example.com"),
                    display_name=DisplayName("Богдан"),
                    password_hash=PasswordHash("$test$"),
                    now=NOW,
                )
            )
            # Напряму SQL-ом: збій репозиторію клієнтів не має ламати фікстуру інших тестів.
            client = make_client()
            await tx.session.execute(
                text(
                    "INSERT INTO oauth_clients (id, name, redirect_uris, registration) "
                    "VALUES (:id, :name, CAST(:uris AS jsonb), CAST(:registration AS jsonb))"
                ),
                {
                    "id": client.id.value,
                    "name": client.name,
                    "uris": json.dumps(client.redirect_uris),
                    "registration": json.dumps(client.metadata),
                },
            )
            await tx.commit()

    portal.call(seed)
    return factory


def make_client(
    client_id: ClientId = CLIENT, name: str | None = "Claude"
) -> OAuthClient:
    return OAuthClient(
        id=client_id,
        name=name,
        redirect_uris=(BINDING.redirect_uri, "http://127.0.0.1:1/cb"),
        metadata={"client_id": str(client_id), "grant_types": ["authorization_code"]},
    )


def make_grant(number: int = 1, *, revoked_at: datetime | None = None) -> Grant:
    return Grant(
        id=GrantId(UUID(int=100 + number)),
        user_id=USER,
        client_id=CLIENT,
        resource=RESOURCE,
        created_at=NOW,
        revoked_at=revoked_at,
    )


def make_token(
    secret: str,
    grant: Grant,
    kind: TokenKind = TokenKind.ACCESS,
    *,
    expires_at: datetime = NOW + timedelta(hours=1),
) -> StoredToken:
    return StoredToken(
        digest=TokenDigest.from_token(secret),
        kind=kind,
        grant_id=grant.id,
        expires_at=expires_at,
        code=BINDING if kind is TokenKind.CODE else None,
    )


class TestClients:
    def test_client_roundtrips_with_its_redirects_and_metadata(
        self, portal: BlockingPortal, uow: UnitOfWorkFactory
    ) -> None:
        async def run() -> OAuthClient | None:
            async with uow() as tx:
                return await tx.oauth_clients.get(CLIENT)

        assert portal.call(run) == make_client()

    def test_client_without_a_name_roundtrips(
        self, portal: BlockingPortal, uow: UnitOfWorkFactory
    ) -> None:
        other = make_client(ClientId(UUID(int=11)), name=None)

        async def run() -> OAuthClient | None:
            async with uow() as tx:
                await tx.oauth_clients.add(other)
                await tx.commit()
            async with uow() as tx:
                return await tx.oauth_clients.get(other.id)

        assert portal.call(run) == other

    def test_unknown_client_is_none(
        self, portal: BlockingPortal, uow: UnitOfWorkFactory
    ) -> None:
        async def run() -> OAuthClient | None:
            async with uow() as tx:
                return await tx.oauth_clients.get(ClientId(UUID(int=99)))

        assert portal.call(run) is None


class TestGrants:
    def test_grant_roundtrips(
        self, portal: BlockingPortal, uow: UnitOfWorkFactory
    ) -> None:
        grant = make_grant()

        async def run() -> Grant | None:
            async with uow() as tx:
                await tx.grants.add(grant)
                await tx.commit()
            async with uow() as tx:
                return await tx.grants.get(grant.id)

        assert portal.call(run) == grant

    def test_revoke_marks_the_grant_once_and_ignores_unknown_ones(
        self, portal: BlockingPortal, uow: UnitOfWorkFactory
    ) -> None:
        grant = make_grant()
        later = NOW + timedelta(minutes=5)

        async def run() -> Grant | None:
            async with uow() as tx:
                await tx.grants.add(grant)
                await tx.commit()
            async with uow() as tx:
                await tx.grants.revoke(grant.id, NOW + timedelta(minutes=1))
                await tx.grants.revoke(grant.id, later)
                await tx.grants.revoke(GrantId(UUID(int=999)), later)
                await tx.commit()
            async with uow() as tx:
                return await tx.grants.get(grant.id)

        revoked = portal.call(run)
        assert revoked is not None
        assert revoked.revoked_at == NOW + timedelta(minutes=1)

    def test_unknown_grant_is_none(
        self, portal: BlockingPortal, uow: UnitOfWorkFactory
    ) -> None:
        async def run() -> Grant | None:
            async with uow() as tx:
                return await tx.grants.get(GrantId(UUID(int=999)))

        assert portal.call(run) is None

    def test_deleting_the_user_deletes_grants_and_their_tokens(
        self, portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
    ) -> None:
        grant = make_grant()

        async def run() -> tuple[int, int]:
            async with uow() as tx:
                await tx.grants.add(grant)
                await tx.oauth_tokens.add(make_token("secret-1", grant))
                await tx.commit()
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM users"))
                grants = (
                    await conn.execute(text("SELECT count(*) FROM oauth_grants"))
                ).scalar_one()
                tokens = (
                    await conn.execute(text("SELECT count(*) FROM oauth_tokens"))
                ).scalar_one()
            return grants, tokens

        assert portal.call(run) == (0, 0)

    def test_grants_without_tokens_are_deleted_and_the_rest_kept(
        self, portal: BlockingPortal, uow: UnitOfWorkFactory
    ) -> None:
        kept, orphan = make_grant(1), make_grant(2)

        async def run() -> tuple[Grant | None, Grant | None]:
            async with uow() as tx:
                await tx.grants.add(kept)
                await tx.grants.add(orphan)
                await tx.oauth_tokens.add(make_token("secret-1", kept))
                await tx.commit()
            async with uow() as tx:
                await tx.grants.delete_without_tokens()
                await tx.commit()
            async with uow() as tx:
                return await tx.grants.get(kept.id), await tx.grants.get(orphan.id)

        assert portal.call(run) == (kept, None)


class TestTokens:
    def test_code_roundtrips_with_its_binding_and_access_token_without_one(
        self, portal: BlockingPortal, uow: UnitOfWorkFactory
    ) -> None:
        grant = make_grant()
        code = make_token("code-1", grant, TokenKind.CODE)
        access = make_token("access-1", grant)

        async def run() -> tuple[StoredToken | None, StoredToken | None]:
            async with uow() as tx:
                await tx.grants.add(grant)
                await tx.oauth_tokens.add(code)
                await tx.oauth_tokens.add(access)
                await tx.commit()
            async with uow() as tx:
                return (
                    await tx.oauth_tokens.find_by_digest(code.digest),
                    await tx.oauth_tokens.find_by_digest(access.digest),
                )

        assert portal.call(run) == (code, access)

    def test_unknown_digest_is_none(
        self, portal: BlockingPortal, uow: UnitOfWorkFactory
    ) -> None:
        async def run() -> StoredToken | None:
            async with uow() as tx:
                return await tx.oauth_tokens.find_by_digest(
                    TokenDigest.from_token("nope")
                )

        assert portal.call(run) is None

    def test_consume_succeeds_once_then_reports_reuse(
        self, portal: BlockingPortal, uow: UnitOfWorkFactory
    ) -> None:
        grant = make_grant()
        refresh = make_token("refresh-1", grant, TokenKind.REFRESH)

        async def run() -> tuple[bool, bool, bool, StoredToken | None]:
            async with uow() as tx:
                await tx.grants.add(grant)
                await tx.oauth_tokens.add(refresh)
                await tx.commit()
            async with uow() as tx:
                first = await tx.oauth_tokens.consume(refresh.digest, NOW)
                await tx.commit()
            async with uow() as tx:
                second = await tx.oauth_tokens.consume(
                    refresh.digest, NOW + timedelta(seconds=5)
                )
                unknown = await tx.oauth_tokens.consume(
                    TokenDigest.from_token("nope"), NOW
                )
                stored = await tx.oauth_tokens.find_by_digest(refresh.digest)
            return first, second, unknown, stored

        first, second, unknown, stored = portal.call(run)
        assert (first, second, unknown) == (True, False, False)
        assert stored is not None
        assert stored.consumed_at == NOW

    def test_expired_tokens_are_deleted_and_live_ones_kept(
        self, portal: BlockingPortal, uow: UnitOfWorkFactory
    ) -> None:
        grant = make_grant()
        old = make_token("old", grant, expires_at=NOW + timedelta(minutes=1))
        live = make_token("live", grant, expires_at=NOW + timedelta(hours=1))

        async def run() -> tuple[StoredToken | None, StoredToken | None]:
            async with uow() as tx:
                await tx.grants.add(grant)
                await tx.oauth_tokens.add(old)
                await tx.oauth_tokens.add(live)
                await tx.commit()
            async with uow() as tx:
                await tx.oauth_tokens.delete_expired(NOW + timedelta(minutes=1))
                await tx.commit()
            async with uow() as tx:
                return (
                    await tx.oauth_tokens.find_by_digest(old.digest),
                    await tx.oauth_tokens.find_by_digest(live.digest),
                )

        assert portal.call(run) == (None, live)


class TestUnusedClients:
    def test_old_clients_without_a_grant_are_deleted_and_the_rest_kept(
        self, portal: BlockingPortal, uow: UnitOfWorkFactory
    ) -> None:
        stale = make_client(ClientId(UUID(int=11)))
        fresh = make_client(ClientId(UUID(int=12)))
        granted = make_client(ClientId(UUID(int=13)))
        grant = Grant(
            id=GrantId(UUID(int=113)),
            user_id=USER,
            client_id=granted.id,
            resource=RESOURCE,
            created_at=NOW,
        )

        async def run() -> tuple[bool, bool, bool]:
            async with uow() as tx:
                await tx.oauth_clients.add(stale, NOW - timedelta(days=40))
                await tx.oauth_clients.add(fresh, NOW - timedelta(days=1))
                await tx.oauth_clients.add(granted, NOW - timedelta(days=40))
                await tx.grants.add(grant)
                await tx.commit()
            async with uow() as tx:
                await tx.oauth_clients.delete_unused(NOW - timedelta(days=30))
                await tx.commit()
            async with uow() as tx:
                return (
                    await tx.oauth_clients.get(stale.id) is not None,
                    await tx.oauth_clients.get(fresh.id) is not None,
                    await tx.oauth_clients.get(granted.id) is not None,
                )

        assert portal.call(run) == (False, True, True)
