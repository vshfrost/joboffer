"""OAuth-сервер через HTTP-маршрути MCP SDK наскрізь: DCR → authorize → код → токени → refresh. Справжній Postgres."""

import base64
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from fastapi.testclient import TestClient
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    IdentityAssertionParams,
    RefreshToken,
    TokenError,
)
from mcp.server.auth.routes import create_auth_routes
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl, AnyUrl
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.applications import Starlette

from application.oauth.use_cases import OAuthServices, OAuthUseCases
from domain.identity.email import Email
from domain.identity.ids import UserId
from domain.identity.password import PasswordHash
from domain.identity.user import DisplayName, User
from domain.oauth.redirect import CLAUDE_CALLBACK
from infrastructure.db.engine import create_engine
from infrastructure.db.unit_of_work import unit_of_work_factory
from infrastructure.mcp.provider import JobofferOAuthProvider
from infrastructure.oauth.audit import LoggingAuditLog
from infrastructure.oauth.pending import InMemoryPendingAuthorizations
from infrastructure.oauth.redirect import RedirectAllowlist
from infrastructure.system import RandomIds, RandomTokens
from tests.support.clock import FakeClock

ISSUER = "http://localhost:8798"
RESOURCE = f"{ISSUER}/joboffer"
USER_A = UserId(UUID(int=1))
USER_B = UserId(UUID(int=2))
VERIFIER = "v" * 64


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    .decode()
    .rstrip("=")
)
REGISTRATION = {
    "redirect_uris": [CLAUDE_CALLBACK],
    "client_name": "Claude",
    "token_endpoint_auth_method": "none",
    "grant_types": ["authorization_code", "refresh_token"],
    "response_types": ["code"],
    "scope": "joboffer",
}


@dataclass
class Stack:
    client: TestClient
    oauth: OAuthUseCases
    provider: JobofferOAuthProvider
    clock: FakeClock
    engine: AsyncEngine

    def call(self, fn: Any, *args: Any) -> Any:
        assert self.client.portal is not None
        return self.client.portal.call(fn, *args)

    def register(self, **overrides: Any) -> httpx2.Response:
        return self.client.post("/register", json={**REGISTRATION, **overrides})

    def client_id(self) -> str:
        response = self.register()
        assert response.status_code == 201, response.text
        return str(response.json()["client_id"])

    def authorize(self, client_id: str, **overrides: str) -> httpx2.Response:
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": CLAUDE_CALLBACK,
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
            "state": "state-xyz",
            "resource": RESOURCE,
            "scope": "joboffer",
            **overrides,
        }
        return self.client.get("/authorize", params=params, follow_redirects=False)

    def login_as(self, user: UserId, client_id: str) -> str:
        """Роль логін-гейта (K7): /authorize → rid → користувач увійшов → код у redirect."""
        response = self.authorize(client_id)
        assert response.status_code == 302, response.text
        location = urlsplit(response.headers["location"])
        assert (
            f"{location.scheme}://{location.netloc}{location.path}"
            == f"{RESOURCE}/login"
        )
        rid = parse_qs(location.query)["rid"][0]
        granted = self.call(self.oauth.complete_authorization, rid, user)
        assert granted.state == "state-xyz"
        return str(granted.code)

    def token(self, **form: str) -> httpx2.Response:
        return self.client.post("/token", data=form)

    def exchange(
        self, client_id: str, code: str, verifier: str = VERIFIER
    ) -> httpx2.Response:
        return self.token(
            grant_type="authorization_code",
            client_id=client_id,
            code=code,
            redirect_uri=CLAUDE_CALLBACK,
            code_verifier=verifier,
        )

    def refresh(
        self, client_id: str, refresh_token: str, **extra: str
    ) -> httpx2.Response:
        return self.token(
            grant_type="refresh_token",
            client_id=client_id,
            refresh_token=refresh_token,
            **extra,
        )

    def tokens_for(self, user: UserId, client_id: str) -> dict[str, Any]:
        response = self.exchange(client_id, self.login_as(user, client_id))
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def access(self, token: str) -> AccessToken | None:
        result: AccessToken | None = self.call(self.provider.load_access_token, token)
        return result


@pytest.fixture
def stack(
    portal: BlockingPortal, engine: AsyncEngine, database_url: str
) -> Iterator[Stack]:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
            await conn.execute(text("TRUNCATE oauth_clients CASCADE"))

    portal.call(clean)
    app_engine = create_engine(database_url)
    uow = unit_of_work_factory(app_engine)
    # SDK порівнює expires_at з реальним time.time(): годинник стартує від справжнього «зараз».
    clock = FakeClock(datetime.now(UTC))
    oauth = OAuthUseCases(
        uow,
        InMemoryPendingAuthorizations(),
        OAuthServices(
            clock=clock,
            ids=RandomIds(),
            tokens=RandomTokens(),
            resource=RESOURCE,
            allowlist=RedirectAllowlist(),
            audit=LoggingAuditLog(),
        ),
    )
    provider = JobofferOAuthProvider(oauth, resource_url=RESOURCE)
    routes = create_auth_routes(
        provider,
        AnyHttpUrl(ISSUER),
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=["joboffer"], default_scopes=["joboffer"]
        ),
        # SDK за замовчуванням не відкриває /revoke; тут вмикаємо, щоб перевірити revoke_token.
        revocation_options=RevocationOptions(enabled=True),
    )
    client = TestClient(Starlette(routes=routes), base_url=ISSUER)
    client.__enter__()
    result = Stack(client, oauth, provider, clock, app_engine)

    async def seed() -> None:
        async with uow() as tx:
            for user_id, email in (
                (USER_A, "a@example.com"),
                (USER_B, "b@example.com"),
            ):
                await tx.users.add(
                    User.register(
                        id=user_id,
                        email=Email(email),
                        display_name=DisplayName("Користувач"),
                        password_hash=PasswordHash("$test$"),
                        now=clock.now(),
                    )
                )
            await tx.commit()

    result.call(seed)
    yield result
    client.__exit__(None, None, None)
    portal.call(app_engine.dispose)


class TestRegistration:
    def test_claude_callback_is_registered_as_a_public_client(
        self, stack: Stack
    ) -> None:
        response = stack.register()

        assert response.status_code == 201
        body = response.json()
        assert body["redirect_uris"] == [CLAUDE_CALLBACK]
        assert body["token_endpoint_auth_method"] == "none"
        assert body.get("client_secret") is None

    def test_client_asking_for_a_secret_still_gets_no_secret(
        self, stack: Stack
    ) -> None:
        response = stack.register(token_endpoint_auth_method="client_secret_post")

        assert response.status_code == 201
        body = response.json()
        assert body["token_endpoint_auth_method"] == "none"
        assert body.get("client_secret") is None

    def test_loopback_redirect_is_accepted(self, stack: Stack) -> None:
        assert (
            stack.register(
                redirect_uris=["http://127.0.0.1:53123/callback"]
            ).status_code
            == 201
        )

    @pytest.mark.parametrize(
        "redirect",
        [
            "https://evil.example/api/mcp/auth_callback",
            "https://claude.ai@evil.example/api/mcp/auth_callback",
            "https://claude.ai:8443/api/mcp/auth_callback",
            "https://claude.ai/api/mcp/../auth_callback",
        ],
    )
    def test_redirect_outside_allowlist_is_invalid_redirect_uri(
        self, stack: Stack, redirect: str
    ) -> None:
        response = stack.register(redirect_uris=[redirect])

        assert response.status_code == 400
        assert response.json()["error"] == "invalid_redirect_uri"


class TestAuthorize:
    def test_authorize_sends_the_user_to_the_login_gate_with_a_request_id(
        self, stack: Stack
    ) -> None:
        response = stack.authorize(stack.client_id())

        assert response.status_code == 302
        location = urlsplit(response.headers["location"])
        assert location.path == "/joboffer/login"
        assert parse_qs(location.query)["rid"][0]

    def test_other_resource_is_invalid_target(self, stack: Stack) -> None:
        response = stack.authorize(
            stack.client_id(), resource="https://evil.example/joboffer"
        )

        assert parse_qs(urlsplit(response.headers["location"]).query)["error"] == [
            "invalid_target"
        ]

    def test_other_scope_is_invalid_scope(self, stack: Stack) -> None:
        response = stack.authorize(stack.client_id(), scope="admin")

        assert parse_qs(urlsplit(response.headers["location"]).query)["error"] == [
            "invalid_scope"
        ]


class TestTokenEndpoint:
    def test_code_for_tokens_whose_subject_is_the_user_who_logged_in(
        self, stack: Stack
    ) -> None:
        client_id = stack.client_id()

        tokens = stack.tokens_for(USER_B, client_id)

        assert (tokens["token_type"], tokens["expires_in"], tokens["scope"]) == (
            "Bearer",
            3600,
            "joboffer",
        )
        access = stack.access(tokens["access_token"])
        assert access is not None
        assert (access.subject, access.client_id, access.scopes, access.resource) == (
            str(USER_B),
            client_id,
            ["joboffer"],
            RESOURCE,
        )
        assert access.claims is not None
        assert access.claims["grant_id"]

    def test_token_of_user_a_never_acts_for_user_b(self, stack: Stack) -> None:
        client_id = stack.client_id()
        token_a = stack.tokens_for(USER_A, client_id)["access_token"]
        token_b = stack.tokens_for(USER_B, client_id)["access_token"]

        access_a, access_b = stack.access(token_a), stack.access(token_b)

        assert access_a is not None
        assert access_b is not None
        assert (access_a.subject, access_b.subject) == (str(USER_A), str(USER_B))

    def test_wrong_code_verifier_is_invalid_grant(self, stack: Stack) -> None:
        client_id = stack.client_id()
        code = stack.login_as(USER_A, client_id)

        response = stack.exchange(client_id, code, verifier="x" * 64)

        assert response.status_code == 400
        assert response.json()["error"] == "invalid_grant"

    def test_expired_code_is_invalid_grant(self, stack: Stack) -> None:
        client_id = stack.client_id()
        code = stack.login_as(USER_A, client_id)
        stack.clock.advance(timedelta(minutes=5))

        response = stack.exchange(client_id, code)

        assert response.status_code == 400
        assert response.json()["error"] == "invalid_grant"

    def test_code_cannot_be_exchanged_twice(self, stack: Stack) -> None:
        client_id = stack.client_id()
        code = stack.login_as(USER_A, client_id)
        first = stack.exchange(client_id, code)
        assert first.status_code == 200

        second = stack.exchange(client_id, code)

        assert second.status_code == 400
        assert second.json()["error"] == "invalid_grant"
        assert stack.access(first.json()["access_token"]) is None

    def test_unknown_client_is_rejected(self, stack: Stack) -> None:
        response = stack.exchange("6f1c0a52-0000-4000-8000-0000000000ff", "code")

        assert response.status_code == 401
        assert response.json()["error"] == "invalid_client"


class TestRefresh:
    def test_refresh_rotates_the_pair_for_the_same_user(self, stack: Stack) -> None:
        client_id = stack.client_id()
        first = stack.tokens_for(USER_A, client_id)

        response = stack.refresh(client_id, first["refresh_token"])

        assert response.status_code == 200
        second = response.json()
        assert second["refresh_token"] != first["refresh_token"]
        access = stack.access(second["access_token"])
        assert access is not None
        assert access.subject == str(USER_A)

    def test_refresh_cannot_widen_the_scope(self, stack: Stack) -> None:
        client_id = stack.client_id()
        tokens = stack.tokens_for(USER_A, client_id)

        response = stack.refresh(
            client_id, tokens["refresh_token"], scope="joboffer admin"
        )

        assert response.status_code == 400
        assert response.json()["error"] == "invalid_scope"

    def test_old_refresh_after_rotation_is_rejected_and_revokes_the_grant(
        self, stack: Stack
    ) -> None:
        client_id = stack.client_id()
        first = stack.tokens_for(USER_A, client_id)
        second = stack.refresh(client_id, first["refresh_token"]).json()

        replay = stack.refresh(client_id, first["refresh_token"])

        assert replay.status_code == 400
        assert replay.json()["error"] == "invalid_grant"
        assert stack.access(second["access_token"]) is None
        assert stack.refresh(client_id, second["refresh_token"]).status_code == 400

    def test_refresh_after_thirty_days_is_invalid_grant(self, stack: Stack) -> None:
        client_id = stack.client_id()
        tokens = stack.tokens_for(USER_A, client_id)
        stack.clock.advance(timedelta(days=30))

        response = stack.refresh(client_id, tokens["refresh_token"])

        assert response.status_code == 400
        assert response.json()["error"] == "invalid_grant"


class TestRevocation:
    def test_revoking_the_access_token_ends_the_grant(self, stack: Stack) -> None:
        client_id = stack.client_id()
        tokens = stack.tokens_for(USER_A, client_id)

        response = stack.client.post(
            "/revoke",
            # SDK вимагає поле client_secret у формі навіть для публічного клієнта (порожнє).
            data={
                "client_id": client_id,
                "client_secret": "",
                "token": tokens["access_token"],
            },
        )

        assert response.status_code == 200
        assert stack.access(tokens["access_token"]) is None
        assert stack.refresh(client_id, tokens["refresh_token"]).status_code == 400


class TestSecretsAtRest:
    def test_tables_hold_no_raw_codes_tokens_or_client_secrets(
        self, stack: Stack
    ) -> None:
        asked_secret = stack.register(token_endpoint_auth_method="client_secret_post")
        client_id = stack.client_id()
        code_for_dump = stack.login_as(USER_A, client_id)
        tokens = stack.exchange(client_id, code_for_dump).json()
        secrets = [
            code_for_dump,
            tokens["access_token"],
            tokens["refresh_token"],
            str(asked_secret.json().get("client_secret") or "no-secret"),
        ]

        async def dump() -> str:
            parts: list[str] = []
            async with stack.engine.connect() as conn:
                for table in ("oauth_clients", "oauth_grants", "oauth_tokens"):
                    rows = await conn.execute(text(f"SELECT t::text FROM {table} t"))  # noqa: S608
                    parts.extend(row[0] for row in rows)
            return json.dumps(parts)

        content = stack.call(dump)
        assert all(secret not in content for secret in secrets)
        assert digest(tokens["access_token"]) in content


class TestProviderDirectly:
    """Захисні гілки адаптера, до яких HTTP-шар SDK не доходить: він сам відсіює такі запити раніше."""

    def client_info(self, client_id: str) -> OAuthClientInformationFull:
        return OAuthClientInformationFull(
            client_id=client_id, redirect_uris=[AnyUrl(CLAUDE_CALLBACK)]
        )

    def test_exchange_of_an_unknown_code_is_invalid_grant(self, stack: Stack) -> None:
        client_id = stack.client_id()
        code = AuthorizationCode(
            code="nope",
            scopes=["joboffer"],
            expires_at=1.0,
            client_id=client_id,
            code_challenge=CHALLENGE,
            redirect_uri=AnyUrl(CLAUDE_CALLBACK),
            redirect_uri_provided_explicitly=True,
        )

        with pytest.raises(TokenError) as caught:
            stack.call(
                stack.provider.exchange_authorization_code,
                self.client_info(client_id),
                code,
            )

        assert caught.value.error == "invalid_grant"

    def test_refresh_exchange_of_an_unknown_token_is_invalid_grant(
        self, stack: Stack
    ) -> None:
        client_id = stack.client_id()
        refresh = RefreshToken(token="nope", client_id=client_id, scopes=["joboffer"])

        with pytest.raises(TokenError) as caught:
            stack.call(
                stack.provider.exchange_refresh_token,
                self.client_info(client_id),
                refresh,
                ["joboffer"],
            )

        assert caught.value.error == "invalid_grant"

    def test_identity_assertion_grant_is_not_supported(self, stack: Stack) -> None:
        with pytest.raises(TokenError) as caught:
            stack.call(
                stack.provider.exchange_identity_assertion,
                self.client_info(stack.client_id()),
                IdentityAssertionParams(assertion="jwt"),
            )

        assert caught.value.error == "unsupported_grant_type"
