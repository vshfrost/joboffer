"""Google у логін-гейті MCP наскрізь: DCR → authorize → Google (фейк на межі HTTP) → код → токен → MCP."""

import base64
import hashlib
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.applications import Starlette

from application.contracts.identity import CreateUser
from bootstrap.agent import create_agent_app
from bootstrap.api import create_app
from bootstrap.container import Container
from bootstrap.settings import Settings
from tests.integration.test_agent_http import (
    BASE,
    CALLBACK,
    PASSWORD,
    PUBLIC,
    SECURITY_HEADERS,
    register_probe,
)
from tests.support.fake_google import (
    CLIENT_ID,
    CLIENT_SECRET,
    ISSUER,
    METADATA_URL,
    FakeGoogle,
    new_key,
)

pytestmark = pytest.mark.anyio

GATE_REDIRECT = f"{PUBLIC}/auth/google/callback"
WEB_REDIRECT = "https://testserver/api/auth/google/callback"
STATE_SECRET = "test-state-secret-0123456789abcdef"
GATE_COOKIE = "joboffer_gate_state"
EMAIL_REQUIRED = "Google не передав підтверджений email — вхід неможливий"
FAILED = "Не вдалося увійти через Google. Спробуй ще раз."


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def google_settings(database_url: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "database_url": database_url,
        "cookie_secure": False,
        "web_public_url": BASE,
        "google_client_id": CLIENT_ID,
        "google_client_secret": CLIENT_SECRET,
        "google_redirect_uri": WEB_REDIRECT,
        "google_gate_redirect_uri": GATE_REDIRECT,
        "google_metadata_url": METADATA_URL,
        "auth_state_secret": STATE_SECRET,
    } | overrides
    return Settings(**values)


@dataclass
class Gate:
    app: Starlette
    http: httpx2.AsyncClient
    container: Container
    google: FakeGoogle
    database_url: str

    async def user(self, email: str = "taras@example.com") -> str:
        created = await self.container.identity.create_user(
            CreateUser(email=email, display_name="Богдан", password=PASSWORD)
        )
        return created.id

    async def signup_request(self, email: str) -> None:
        """Незавершена реєстрація: запит є, користувача ще нема."""
        insert = text(
            "INSERT INTO signup_requests (id, email, password_hash, display_name, invite_digest, terms_version,"
            " code_digest, failed_attempts, created_at, sent_at, expires_at) VALUES"
            " (gen_random_uuid(), :email, 'x', 'Богдан', 'i', '2026-10-28', 'c', 0, now(), now(), now() + interval '1 hour')"
        )
        async with self.container.engine.begin() as conn:
            await conn.execute(insert, {"email": email})

    async def count(self, table: str) -> int:
        async with self.container.engine.connect() as conn:
            result = await conn.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
            return int(result.scalar_one())

    async def begin(self, name: str = "Claude") -> tuple[str, str, str]:
        """DCR + /authorize → (client_id, verifier, rid)."""
        registered = await self.http.post(
            "/register",
            json={
                "redirect_uris": [CALLBACK],
                "client_name": name,
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
        )
        client_id = str(registered.json()["client_id"])
        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        authorized = await self.http.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": CALLBACK,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "st-1",
                "scope": "joboffer",
                "resource": PUBLIC,
            },
        )
        rid = parse_qs(urlsplit(authorized.headers["location"]).query)["rid"][0]
        return client_id, verifier, rid

    async def to_google(self, rid: str) -> tuple[str, str]:
        """Кнопка Google: повертає `state` і `nonce` із посилання на Google."""
        response = await self.http.get("/auth/google/start", params={"rid": rid})
        assert response.status_code == 302, response.text
        query = parse_qs(urlsplit(response.headers["location"]).query)
        return query["state"][0], query["nonce"][0]

    async def back(self, state: str, **params: str) -> httpx2.Response:
        return await self.http.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state, **params},
        )

    async def google_sign_in(self, rid: str, **claims: Any) -> httpx2.Response:
        state, nonce = await self.to_google(rid)
        self.google.prepare(nonce, **claims)
        return await self.back(state)

    async def exchange(
        self, client_id: str, verifier: str, location: str
    ) -> dict[str, Any]:
        params = parse_qs(urlsplit(location).query)
        response = await self.http.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": params["code"][0],
                "redirect_uri": CALLBACK,
                "client_id": client_id,
                "code_verifier": verifier,
                "resource": PUBLIC,
            },
        )
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def authed(self, token: str) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=self.app),
            base_url=BASE,
            headers={"Authorization": f"Bearer {token}"},
        )


@pytest.fixture
async def gate(
    portal: BlockingPortal, engine: AsyncEngine, database_url: str
) -> AsyncIterator[Gate]:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
            await conn.execute(text("TRUNCATE signup_requests"))
            await conn.execute(text("TRUNCATE oauth_clients CASCADE"))
            await conn.execute(text("TRUNCATE login_failures"))

    portal.call(clean)
    google = FakeGoogle()
    app = create_agent_app(
        google_settings(database_url),
        tools=register_probe,
        google_transport=httpx2.ASGITransport(app=google.app()),
    )
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=BASE
        ) as http,
    ):
        yield Gate(app, http, app.state.container, google, database_url)


class TestButton:
    async def test_the_gate_page_offers_google_when_it_is_configured(
        self, gate: Gate
    ) -> None:
        _, _, rid = await gate.begin()

        page = await gate.http.get("/login", params={"rid": rid})

        assert f'href="auth/google/start?rid={rid}"' in page.text
        assert "Увійти через Google" in page.text
        assert 'type="password"' in page.text

    async def test_the_old_login_google_paths_are_gone(self, gate: Gate) -> None:
        _, _, rid = await gate.begin()

        start = await gate.http.get("/login/google", params={"rid": rid})
        callback = await gate.http.get(
            "/login/google/callback", params={"code": "c", "state": "s"}
        )

        assert start.status_code == 404
        assert callback.status_code == 404

    async def test_the_gate_page_has_no_google_without_the_gate_redirect_uri(
        self, portal: BlockingPortal, engine: AsyncEngine, database_url: str
    ) -> None:
        app = create_agent_app(
            google_settings(database_url, google_gate_redirect_uri=None)
        )
        async with (
            app.router.lifespan_context(app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app), base_url=BASE
            ) as http,
        ):
            other = Gate(app, http, app.state.container, FakeGoogle(), database_url)
            _, _, rid = await other.begin()

            page = await http.get("/login", params={"rid": rid})
            start = await http.get("/auth/google/start", params={"rid": rid})

        assert "Google" not in page.text
        assert start.status_code == 404

    async def test_clicking_it_sends_the_browser_to_google_with_the_gate_callback(
        self, gate: Gate
    ) -> None:
        _, _, rid = await gate.begin()

        response = await gate.http.get("/auth/google/start", params={"rid": rid})

        assert response.status_code == 302
        target = urlsplit(response.headers["location"])
        query = parse_qs(target.query)
        assert (
            f"{target.scheme}://{target.netloc}{target.path}" == f"{ISSUER}/authorize"
        )
        assert query["redirect_uri"] == [
            "http://127.0.0.1:8798/mcp/auth/google/callback"
        ]
        assert query["client_id"] == [CLIENT_ID]
        assert query["code_challenge_method"] == ["S256"]
        assert query["state"][0]
        assert query["nonce"][0]
        assert GATE_COOKIE in response.headers["set-cookie"]

    @pytest.mark.parametrize("rid", ["", "no-such-request"])
    async def test_without_a_live_request_there_is_no_trip_to_google(
        self, gate: Gate, rid: str
    ) -> None:
        response = await gate.http.get("/auth/google/start", params={"rid": rid})

        assert response.status_code == 400
        assert "застарів" in response.text
        assert "location" not in response.headers


class TestSignIn:
    async def test_verified_google_email_of_an_existing_user_ends_in_a_redirect_with_a_code_and_a_working_token(
        self, gate: Gate
    ) -> None:
        await gate.user("katya@example.com")
        client_id, verifier, rid = await gate.begin()

        back = await gate.google_sign_in(
            rid, email="katya@example.com", name="Наталя", sub="sub-katya"
        )

        assert back.status_code == 302
        assert back.headers["location"].startswith(f"{CALLBACK}?")
        assert parse_qs(urlsplit(back.headers["location"]).query)["state"] == ["st-1"]
        issued = await gate.exchange(client_id, verifier, back.headers["location"])
        async with (
            gate.authed(issued["access_token"]) as authed,
            Client(streamable_http_client(PUBLIC, http_client=authed)) as client,
        ):
            who = (await client.call_tool("whoami", {})).structured_content
        assert who is not None
        assert who["channel"] == "mcp"
        assert who["client_id"] == client_id
        view = await gate.container.oauth.verify_access(issued["access_token"])
        assert view is not None
        assert who["user_id"] == str(view.user_id)
        assert who["grant_id"] == str(view.grant_id)

    async def test_existing_password_user_is_the_one_the_token_acts_for(
        self, gate: Gate
    ) -> None:
        created = await gate.user()
        client_id, verifier, rid = await gate.begin()

        back = await gate.google_sign_in(rid)

        issued = await gate.exchange(client_id, verifier, back.headers["location"])
        view = await gate.container.oauth.verify_access(issued["access_token"])
        assert view is not None
        assert str(view.user_id) == created

    async def test_full_flow_ends_with_tools_list_through_the_sdk_client(
        self, gate: Gate
    ) -> None:
        await gate.user()
        client_id, verifier, rid = await gate.begin()
        back = await gate.google_sign_in(rid)
        issued = await gate.exchange(client_id, verifier, back.headers["location"])

        async with (
            gate.authed(issued["access_token"]) as authed,
            Client(streamable_http_client(PUBLIC, http_client=authed)) as client,
        ):
            names = {tool.name for tool in (await client.list_tools()).tools}

        assert names == {"whoami"}

    async def test_the_request_id_is_spent_by_a_successful_google_sign_in(
        self, gate: Gate
    ) -> None:
        await gate.user()
        _, _, rid = await gate.begin()
        state, nonce = await gate.to_google(rid)
        gate.google.prepare(nonce)
        assert (await gate.back(state)).status_code == 302

        again = await gate.http.post(
            "/login",
            data={"rid": rid, "email": "taras@example.com", "password": PASSWORD},
        )

        assert again.status_code == 400
        assert "застарів" in again.text


class TestRefusals:
    @pytest.mark.parametrize(
        "claims",
        [{"email": None}, {"email_verified": False}, {"email": "not-an-email"}],
    )
    async def test_no_usable_verified_email_shows_the_gate_page_with_the_error_and_no_code(
        self, gate: Gate, claims: dict[str, Any]
    ) -> None:
        _, _, rid = await gate.begin()

        response = await gate.google_sign_in(rid, **claims)

        assert response.status_code == 400
        assert "location" not in response.headers
        assert EMAIL_REQUIRED in response.text
        assert f'name="rid" value="{rid}"' in response.text

    async def test_email_absent_from_users_shows_the_same_error_and_creates_nothing(
        self, gate: Gate
    ) -> None:
        _, _, rid = await gate.begin()

        response = await gate.google_sign_in(rid, email="stranger@example.com")

        assert response.status_code == 400
        assert "location" not in response.headers
        assert EMAIL_REQUIRED in response.text
        assert f'name="rid" value="{rid}"' in response.text
        assert (await gate.count("users"), await gate.count("user_identities")) == (
            0,
            0,
        )

    async def test_email_only_in_an_unfinished_signup_shows_the_same_error_and_creates_nothing(
        self, gate: Gate
    ) -> None:
        await gate.signup_request("taras@example.com")
        _, _, rid = await gate.begin()

        response = await gate.google_sign_in(rid)

        assert response.status_code == 400
        assert "location" not in response.headers
        assert EMAIL_REQUIRED in response.text
        assert (await gate.count("users"), await gate.count("user_identities")) == (
            0,
            0,
        )
        assert await gate.count("signup_requests") == 1

    async def test_the_request_id_survives_a_refusal_so_the_password_still_works(
        self, gate: Gate
    ) -> None:
        await gate.user()
        _, _, rid = await gate.begin()
        refused = await gate.google_sign_in(rid, email_verified=False)
        assert refused.status_code == 400

        response = await gate.http.post(
            "/login",
            data={"rid": rid, "email": "taras@example.com", "password": PASSWORD},
        )

        assert response.status_code == 302
        assert "code=" in response.headers["location"]

    async def test_unverified_email_of_a_password_user_is_not_linked(
        self, gate: Gate
    ) -> None:
        await gate.user()
        _, _, rid = await gate.begin()

        await gate.google_sign_in(rid, email_verified=False)

        async with gate.container.engine.connect() as conn:
            count = (
                await conn.execute(text("SELECT count(*) FROM user_identities"))
            ).scalar_one()
        assert count == 0

    @pytest.mark.parametrize(
        "claims",
        [
            {"nonce_override": "a-different-nonce"},
            {"key": "other-key"},
            {"aud": "someone-else"},
        ],
    )
    async def test_wrong_nonce_signature_or_audience_shows_the_failure_and_no_code(
        self, gate: Gate, claims: dict[str, Any]
    ) -> None:
        _, _, rid = await gate.begin()
        state, nonce = await gate.to_google(rid)
        overrides = dict(claims)
        nonce = str(overrides.pop("nonce_override", nonce))
        if "key" in overrides:
            overrides["key"] = new_key()
        gate.google.prepare(nonce, **overrides)

        response = await gate.back(state)

        assert response.status_code == 400
        assert "location" not in response.headers
        assert FAILED in response.text
        assert f'name="rid" value="{rid}"' in response.text

    async def test_wrong_state_shows_the_failure_and_no_code(self, gate: Gate) -> None:
        _, _, rid = await gate.begin()
        _, nonce = await gate.to_google(rid)
        gate.google.prepare(nonce)

        response = await gate.back("not-the-state")

        assert response.status_code == 400
        assert "location" not in response.headers
        assert gate.google.token_requests == []

    async def test_a_failed_attempt_spends_the_started_flow_but_not_the_request(
        self, gate: Gate
    ) -> None:
        _, _, rid = await gate.begin()
        state, nonce = await gate.to_google(rid)
        gate.google.prepare(nonce, aud="someone-else")
        await gate.back(state)

        replay = await gate.back(state)

        assert replay.status_code == 400
        assert "застарів" in replay.text
        assert "Увійти" in (await gate.http.get("/login", params={"rid": rid})).text

    async def test_cancelling_at_google_shows_the_cancellation(
        self, gate: Gate
    ) -> None:
        _, _, rid = await gate.begin()
        state, _ = await gate.to_google(rid)

        response = await gate.http.get(
            "/auth/google/callback", params={"error": "access_denied", "state": state}
        )

        assert response.status_code == 400
        assert "Вхід скасовано" in response.text
        assert "location" not in response.headers

    async def test_google_returns_to_the_gate_callback_under_mcp_of_the_origin(
        self, gate: Gate
    ) -> None:
        _, _, rid = await gate.begin()
        state, _ = await gate.to_google(rid)

        response = await gate.http.get(
            "/mcp/auth/google/callback",
            params={"error": "access_denied", "state": state},
        )

        assert response.status_code == 400
        assert "Вхід скасовано" in response.text

    async def test_a_request_id_spent_while_the_user_was_at_google_means_no_code(
        self, gate: Gate
    ) -> None:
        await gate.user()
        _, _, rid = await gate.begin()
        state, nonce = await gate.to_google(rid)
        gate.google.prepare(nonce)
        spent = await gate.http.post(
            "/login",
            data={"rid": rid, "email": "taras@example.com", "password": PASSWORD},
        )
        assert spent.status_code == 302

        response = await gate.back(state)

        assert response.status_code == 400
        assert "застарів" in response.text
        assert "location" not in response.headers

    async def test_callback_without_a_started_flow_is_stale(self, gate: Gate) -> None:
        response = await gate.back("any-state")

        assert response.status_code == 400
        assert "застарів" in response.text

    async def test_pages_carry_the_strict_security_headers(self, gate: Gate) -> None:
        _, _, rid = await gate.begin()
        state, nonce = await gate.to_google(rid)
        gate.google.prepare(nonce, email_verified=False)
        responses = [
            await gate.back(state),
            await gate.http.get("/auth/google/start", params={"rid": "nope"}),
            await gate.http.get("/login", params={"rid": rid}),
        ]

        for response in responses:
            for name, value in SECURITY_HEADERS.items():
                assert response.headers[name] == value, (response.status_code, name)


class TestFlowsAreSeparate:
    async def test_a_state_from_the_web_flow_is_not_accepted_by_the_gate(
        self, gate: Gate
    ) -> None:
        await gate.begin()
        web = create_app(
            google_settings(gate.database_url),
            google_transport=httpx2.ASGITransport(app=gate.google.app()),
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=web), base_url="http://127.0.0.1:8797"
        ) as web_http:
            started = await web_http.get("/auth/google/start", params={"next": "/"})
            web_state, web_nonce = (
                parse_qs(urlsplit(started.headers["location"]).query)[key][0]
                for key in ("state", "nonce")
            )
            gate.google.prepare(web_nonce)

            for name, value in web_http.cookies.items():
                gate.http.cookies.set(name, value)

            response = await gate.http.get(
                "/auth/google/callback",
                params={"code": "auth-code", "state": web_state},
            )

        assert response.status_code == 400
        assert "location" not in response.headers

    async def test_a_state_from_the_gate_is_not_accepted_by_the_web_flow(
        self, gate: Gate
    ) -> None:
        _, _, rid = await gate.begin()
        gate_state, gate_nonce = await gate.to_google(rid)
        gate.google.prepare(gate_nonce)
        web = create_app(
            google_settings(gate.database_url),
            google_transport=httpx2.ASGITransport(app=gate.google.app()),
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=web), base_url="http://127.0.0.1:8797"
        ) as web_http:
            for name, value in gate.http.cookies.items():
                web_http.cookies.set(name, value)

            response = await web_http.get(
                "/auth/google/callback",
                params={"code": "auth-code", "state": gate_state},
            )

        assert response.status_code == 302
        assert response.headers["location"].endswith("/login?error=invalid_state")
        assert "joboffer_session" not in response.headers.get("set-cookie", "")

    async def test_the_gate_and_the_web_use_different_state_cookies(
        self, gate: Gate
    ) -> None:
        _, _, rid = await gate.begin()

        response = await gate.http.get("/auth/google/start", params={"rid": rid})

        assert "joboffer_oauth_state" not in response.headers["set-cookie"]
        assert GATE_COOKIE in response.headers["set-cookie"]
