"""Агент (MCP + OAuth) як ASGI-застосунок на справжньому Postgres: логін-гейт, токени, Actor, захист транспорту."""

import base64
import hashlib
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from mcp.client import Client
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from pydantic import AnyUrl, BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.applications import Starlette

from application.contracts.identity import CreateUser
from bootstrap.agent import create_agent_app
from bootstrap.container import Container
from bootstrap.settings import Settings
from infrastructure.mcp.actor import current_actor

pytestmark = pytest.mark.anyio

BASE = "http://127.0.0.1:8798"
MCP_PATH = "/mcp"
PUBLIC = f"{BASE}{MCP_PATH}"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"
PASSWORD = "correct horse battery"
OTHER_PASSWORD = "another long password"
INSTRUCTIONS = (
    Path(__file__).resolve().parents[2] / "prompts" / "mcp" / "instructions.md"
).read_text(encoding="utf-8")
INVALID_CREDENTIALS = "Невірний email або пароль"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Whoami(BaseModel):
    user_id: str
    channel: str
    client_id: str
    grant_id: str
    scopes: list[str]
    correlation_id: str


def register_probe(agent: MCPServer, container: Container) -> None:
    """Тул лише для тестів: показує Actor, якого дістав би будь-який майбутній тул."""

    @agent.tool()
    def whoami() -> Whoami:
        actor = current_actor()
        return Whoami(
            user_id=str(actor.user_id),
            channel=actor.channel.value,
            client_id=actor.client_id,
            grant_id=str(actor.grant_id),
            scopes=sorted(scope.value for scope in actor.scopes),
            correlation_id=actor.correlation_id,
        )


@dataclass
class Agent:
    app: Starlette
    http: httpx2.AsyncClient
    container: Container
    user_ids: dict[str, str]

    def authed(self, token: str) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=self.app),
            base_url=BASE,
            headers={"Authorization": f"Bearer {token}"},
        )


@pytest.fixture
async def agent(
    portal: BlockingPortal, engine: AsyncEngine, database_url: str
) -> AsyncIterator[Agent]:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
            await conn.execute(text("TRUNCATE oauth_clients CASCADE"))
            await conn.execute(text("TRUNCATE login_failures"))

    portal.call(clean)
    app = create_agent_app(
        Settings(environment="test", database_url=database_url, web_public_url=BASE),
        tools=register_probe,
    )
    container: Container = app.state.container
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=BASE
        ) as http,
    ):
        user_ids = {}
        for email, name, password in (
            ("taras@example.com", "Богдан", PASSWORD),
            ("katya@example.com", "Наталя", OTHER_PASSWORD),
        ):
            created = await container.identity.create_user(
                CreateUser(email=email, display_name=name, password=password)
            )
            user_ids[email] = created.id
        yield Agent(app, http, container, user_ids)


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge.rstrip(b"=").decode()


def query(location: str) -> dict[str, str]:
    return {
        key: values[0] for key, values in parse_qs(urlsplit(location).query).items()
    }


async def register(agent: Agent, name: str = "Claude") -> str:
    response = await agent.http.post(
        "/register",
        json={
            "redirect_uris": [CALLBACK],
            "client_name": name,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["client_id"])


async def begin(agent: Agent, client_id: str, challenge: str) -> str:
    """/authorize → rid із посилання на логін-гейт."""
    response = await agent.http.get(
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
    assert response.status_code == 302, response.text
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{PUBLIC}/login"
    return query(response.headers["location"])["rid"]


async def sign_in(
    agent: Agent, rid: str, email: str = "taras@example.com", password: str = PASSWORD
) -> httpx2.Response:
    return await agent.http.post(
        "/login", data={"rid": rid, "email": email, "password": password}
    )


async def tokens_for(
    agent: Agent, email: str = "taras@example.com", password: str = PASSWORD
) -> dict[str, str]:
    client_id = await register(agent)
    verifier, challenge = pkce()
    rid = await begin(agent, client_id, challenge)
    back = await sign_in(agent, rid, email, password)
    assert back.status_code == 302, back.text
    params = query(back.headers["location"])
    assert params["state"] == "st-1"
    response = await agent.http.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": params["code"],
            "redirect_uri": CALLBACK,
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": PUBLIC,
        },
    )
    assert response.status_code == 200, response.text
    return {**response.json(), "client_id": client_id}


async def whoami(agent: Agent, token: str) -> dict[str, object]:
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            result = await client.call_tool("whoami", {})
    assert result.structured_content is not None
    return dict(result.structured_content)


SECURITY_HEADERS = {
    "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
}


class TestTransport:
    async def test_mcp_without_a_token_is_401_pointing_to_the_resource_metadata(
        self, agent: Agent
    ) -> None:
        response = await agent.http.post(MCP_PATH, json={})

        assert response.status_code == 401
        assert (
            f'resource_metadata="{BASE}/.well-known/oauth-protected-resource/mcp"'
            in response.headers["www-authenticate"]
        )

    async def test_protected_resource_document_names_the_mcp_url_of_the_origin(
        self, agent: Agent
    ) -> None:
        response = await agent.http.get("/.well-known/oauth-protected-resource/mcp")

        assert response.status_code == 200
        resource = response.json()
        assert resource["resource"].rstrip("/") == "http://127.0.0.1:8798/mcp"
        assert [url.rstrip("/") for url in resource["authorization_servers"]] == [
            "http://127.0.0.1:8798/mcp"
        ]
        assert resource["scopes_supported"] == ["joboffer"]

    async def test_authorization_server_document_for_the_mcp_issuer_puts_endpoints_under_mcp(
        self, agent: Agent
    ) -> None:
        response = await agent.http.get("/.well-known/oauth-authorization-server/mcp")

        assert response.status_code == 200
        server = response.json()
        assert server["issuer"].rstrip("/") == "http://127.0.0.1:8798/mcp"
        assert server["authorization_endpoint"] == "http://127.0.0.1:8798/mcp/authorize"
        assert server["token_endpoint"] == "http://127.0.0.1:8798/mcp/token"
        assert server["registration_endpoint"] == "http://127.0.0.1:8798/mcp/register"

    async def test_root_authorization_server_document_agrees_with_the_issuer_one(
        self, agent: Agent
    ) -> None:
        root = (await agent.http.get("/.well-known/oauth-authorization-server")).json()

        assert root["issuer"].rstrip("/") == "http://127.0.0.1:8798/mcp"
        assert root["authorization_endpoint"] == "http://127.0.0.1:8798/mcp/authorize"

    async def test_browser_origin_is_refused_even_with_a_valid_token(
        self, agent: Agent
    ) -> None:
        token = (await tokens_for(agent))["access_token"]

        response = await agent.http.post(
            MCP_PATH,
            json={},
            headers={
                "Authorization": f"Bearer {token}",
                "Origin": "https://evil.example",
            },
        )

        assert response.status_code == 403

    async def test_unknown_host_is_refused_even_with_a_valid_token(
        self, agent: Agent
    ) -> None:
        token = (await tokens_for(agent))["access_token"]

        response = await agent.http.post(
            MCP_PATH,
            json={},
            headers={"Authorization": f"Bearer {token}", "Host": "evil.example"},
        )

        assert response.status_code == 421

    async def test_healthz_is_open_and_reports_ok(self, agent: Agent) -> None:
        response = await agent.http.get("/healthz")

        assert (response.status_code, response.json()) == (200, {"status": "ok"})

    async def test_healthz_is_503_when_the_database_is_down(self) -> None:
        app = create_agent_app(
            Settings(
                environment="test",
                database_url="postgresql+psycopg://nobody:nothing@127.0.0.1:1/none",
                web_public_url=BASE,
            )
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=BASE
        ) as http:
            response = await http.get("/healthz")

        assert response.status_code == 503
        assert response.json() == {"status": "database unavailable"}


class TestLoginGatePages:
    async def test_without_a_request_id_there_is_no_form(self, agent: Agent) -> None:
        response = await agent.http.get("/login")

        assert response.status_code == 200
        assert "<form" not in response.text
        assert 'name="password"' not in response.text

    async def test_with_an_unknown_request_id_there_is_no_form(
        self, agent: Agent
    ) -> None:
        response = await agent.http.get("/login", params={"rid": "no-such-request"})

        assert response.status_code == 200
        assert "<form" not in response.text
        assert "застарів" in response.text

    async def test_with_a_live_request_id_it_shows_consent_and_the_form(
        self, agent: Agent
    ) -> None:
        rid = await begin(agent, await register(agent), pkce()[1])

        response = await agent.http.get("/login", params={"rid": rid})

        assert response.status_code == 200
        assert "Claude" in response.text  # хто просить доступ
        assert "claude.ai" in response.text  # куди піде код
        assert f'name="rid" value="{rid}"' in response.text
        assert 'type="email"' in response.text
        assert 'type="password"' in response.text

    async def test_client_name_is_escaped(self, agent: Agent) -> None:
        client_id = await register(agent, name="<script>alert(1)</script>")
        rid = await begin(agent, client_id, pkce()[1])

        response = await agent.http.get("/login", params={"rid": rid})

        assert "<script>alert(1)" not in response.text
        assert "&lt;script&gt;" in response.text

    async def test_pages_carry_strict_security_headers(self, agent: Agent) -> None:
        rid = await begin(agent, await register(agent), pkce()[1])
        responses = [
            await agent.http.get("/login"),
            await agent.http.get("/login", params={"rid": "nope"}),
            await agent.http.get("/login", params={"rid": rid}),
            await sign_in(agent, rid, password="wrong password here"),
            await sign_in(agent, "nope"),
        ]

        for response in responses:
            for name, value in SECURITY_HEADERS.items():
                assert response.headers[name] == value, (response.status_code, name)


class TestLoginGateSignIn:
    async def test_wrong_password_and_unknown_email_look_the_same(
        self, agent: Agent
    ) -> None:
        rid = await begin(agent, await register(agent), pkce()[1])

        wrong_password = await sign_in(agent, rid, password="wrong password here")
        unknown_email = await sign_in(agent, rid, email="nobody@example.com")

        assert (wrong_password.status_code, unknown_email.status_code) == (401, 401)
        assert INVALID_CREDENTIALS in wrong_password.text
        assert INVALID_CREDENTIALS in unknown_email.text

    async def test_the_form_comes_back_with_the_email_but_never_the_password(
        self, agent: Agent
    ) -> None:
        rid = await begin(agent, await register(agent), pkce()[1])

        response = await sign_in(agent, rid, password="wrong password here")

        assert 'value="taras@example.com"' in response.text
        assert "wrong password here" not in response.text
        assert f'name="rid" value="{rid}"' in response.text

    async def test_five_failures_block_the_pair_with_retry_after(
        self, agent: Agent
    ) -> None:
        rid = await begin(agent, await register(agent), pkce()[1])
        for _ in range(5):
            assert (
                await sign_in(agent, rid, password="wrong password here")
            ).status_code == 401

        blocked = await sign_in(agent, rid)

        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        assert "Забагато спроб" in blocked.text

    async def test_another_email_is_not_blocked_by_failures_of_the_first(
        self, agent: Agent
    ) -> None:
        rid = await begin(agent, await register(agent), pkce()[1])
        for _ in range(5):
            await sign_in(agent, rid, password="wrong password here")

        other = await sign_in(
            agent, rid, email="katya@example.com", password=OTHER_PASSWORD
        )

        assert other.status_code == 302

    async def test_a_stale_request_id_is_rejected_whatever_the_password(
        self, agent: Agent
    ) -> None:
        response = await sign_in(agent, "no-such-request")

        assert response.status_code == 400
        assert "застарів" in response.text
        assert "location" not in response.headers

    async def test_success_redirects_back_to_the_client_with_a_code_and_its_state(
        self, agent: Agent
    ) -> None:
        rid = await begin(agent, await register(agent), pkce()[1])

        response = await sign_in(agent, rid, "katya@example.com", OTHER_PASSWORD)

        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith(f"{CALLBACK}?")
        params = query(location)
        assert params["state"] == "st-1"
        assert params["code"]

    async def test_the_request_id_works_once(self, agent: Agent) -> None:
        rid = await begin(agent, await register(agent), pkce()[1])
        assert (await sign_in(agent, rid)).status_code == 302

        assert (await sign_in(agent, rid)).status_code == 400


class TestTokenEndpointResourceGuard:
    async def exchange(self, agent: Agent, **extra: str) -> httpx2.Response:
        client_id = await register(agent)
        verifier, challenge = pkce()
        rid = await begin(agent, client_id, challenge)
        params = query((await sign_in(agent, rid)).headers["location"])
        data = {
            "grant_type": "authorization_code",
            "code": params["code"],
            "redirect_uri": CALLBACK,
            "client_id": client_id,
            "code_verifier": verifier,
        }
        return await agent.http.post("/token", data=data | extra)

    async def test_another_resource_is_invalid_target(self, agent: Agent) -> None:
        response = await self.exchange(agent, resource="https://evil.example/sample")

        assert response.status_code == 400
        assert response.json() == {"error": "invalid_target"}

    async def test_the_servers_own_resource_and_no_resource_are_fine(
        self, agent: Agent
    ) -> None:
        assert (await self.exchange(agent, resource=PUBLIC)).status_code == 200
        assert (await self.exchange(agent)).status_code == 200

    async def test_oversized_token_request_is_413(self, agent: Agent) -> None:
        response = await agent.http.post("/token", data={"junk": "x" * 70_000})

        assert response.status_code == 413


class TestIssuedToken:
    async def test_a_freshly_issued_token_is_accepted(self, agent: Agent) -> None:
        issued = await tokens_for(agent)

        async with agent.authed(issued["access_token"]) as authed:
            response = await authed.post(MCP_PATH, json={})

        assert response.status_code != 401


class MemoryStorage:
    def __init__(self) -> None:
        self.tokens: OAuthToken | None = None
        self.client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.client_info = client_info


class TestSdkClientFromTheOriginRoot:
    async def test_dcr_login_token_and_tools_list_work_from_the_origin_alone(
        self, agent: Agent
    ) -> None:
        storage = MemoryStorage()
        callback: list[AuthorizationCodeResult] = []

        async def redirect(authorization_url: str) -> None:
            parts = urlsplit(authorization_url)
            assert (parts.scheme, parts.netloc) == ("http", "127.0.0.1:8798")
            assert parts.path == "/mcp/authorize"
            authorize = await agent.http.get(f"{parts.path}?{parts.query}")
            assert authorize.status_code == 302, authorize.text
            login = urlsplit(authorize.headers["location"])
            assert login.path == "/mcp/login"
            rid = query(authorize.headers["location"])["rid"]
            back = await agent.http.post(
                login.path,
                data={"rid": rid, "email": "taras@example.com", "password": PASSWORD},
            )
            assert back.status_code == 302, back.text
            params = query(back.headers["location"])
            callback.append(
                AuthorizationCodeResult(code=params["code"], state=params["state"])
            )

        async def wait_for_code() -> AuthorizationCodeResult:
            return callback[0]

        provider = OAuthClientProvider(
            server_url=PUBLIC,
            client_metadata=OAuthClientMetadata(
                client_name="Claude",
                redirect_uris=[AnyUrl(CALLBACK)],
                token_endpoint_auth_method="none",
                scope="joboffer",
            ),
            storage=storage,
            redirect_handler=redirect,
            callback_handler=wait_for_code,
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=agent.app), base_url=BASE, auth=provider
        ) as http:
            transport = streamable_http_client(PUBLIC, http_client=http)
            async with Client(transport) as client:
                names = {tool.name for tool in (await client.list_tools()).tools}

        assert names == {"whoami"}
        assert storage.client_info is not None
        assert storage.tokens is not None


class TestActorAndTools:
    async def test_token_acts_as_the_user_who_signed_in_through_the_mcp_channel(
        self, agent: Agent
    ) -> None:
        issued = await tokens_for(agent, "katya@example.com", OTHER_PASSWORD)

        who = await whoami(agent, issued["access_token"])

        view = await agent.container.oauth.verify_access(issued["access_token"])
        assert view is not None
        assert who["user_id"] == agent.user_ids["katya@example.com"]
        assert who["channel"] == "mcp"
        assert who["client_id"] == issued["client_id"]
        assert who["grant_id"] == str(view.grant_id)
        assert who["scopes"] == ["read", "write"]
        assert who["correlation_id"]

    async def test_tokens_of_two_users_never_swap_identities(
        self, agent: Agent
    ) -> None:
        taras = await tokens_for(agent)
        katya = await tokens_for(agent, "katya@example.com", OTHER_PASSWORD)

        assert (await whoami(agent, taras["access_token"]))[
            "user_id"
        ] == agent.user_ids["taras@example.com"]
        assert (await whoami(agent, katya["access_token"]))[
            "user_id"
        ] == agent.user_ids["katya@example.com"]

    async def test_every_call_gets_its_own_correlation_id(self, agent: Agent) -> None:
        token = (await tokens_for(agent))["access_token"]

        first, second = await whoami(agent, token), await whoami(agent, token)

        assert first["correlation_id"] != second["correlation_id"]

    async def test_initialize_returns_the_instructions_from_the_prompt_file(
        self, agent: Agent
    ) -> None:
        token = (await tokens_for(agent))["access_token"]

        async with agent.authed(token) as authed:
            transport = streamable_http_client(PUBLIC, http_client=authed)
            async with Client(transport) as client:
                instructions = client.instructions

        assert instructions == INSTRUCTIONS

    async def test_full_flow_ends_with_tools_list_through_the_sdk_client(
        self, agent: Agent
    ) -> None:
        issued = await tokens_for(agent)

        async with agent.authed(issued["access_token"]) as authed:
            transport = streamable_http_client(PUBLIC, http_client=authed)
            async with Client(transport) as client:
                names = {tool.name for tool in (await client.list_tools()).tools}

        assert names == {"whoami"}


class TestPrefixedPaths:
    """Edge (Caddy, Tunnel, Vite) веде `/mcp*` на агента без зміни шляху: метадані оголошують endpoint-и
    як `<origin>/mcp/authorize` тощо, тож вони мають працювати з префіксом `/mcp`."""

    async def test_every_advertised_endpoint_exists_under_the_prefix(
        self, agent: Agent
    ) -> None:
        metadata = (
            await agent.http.get("/.well-known/oauth-authorization-server")
        ).json()

        registration = await agent.http.post(
            urlsplit(metadata["registration_endpoint"]).path,
            json={
                "redirect_uris": [CALLBACK],
                "client_name": "Claude",
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
        )
        client_id = registration.json()["client_id"]
        authorize = await agent.http.get(
            urlsplit(metadata["authorization_endpoint"]).path,
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": CALLBACK,
                "code_challenge": pkce()[1],
                "code_challenge_method": "S256",
                "state": "st-1",
                "scope": "joboffer",
                "resource": PUBLIC,
            },
        )
        login = await agent.http.get(
            urlsplit(authorize.headers["location"]).path, params={"rid": "x"}
        )
        token = await agent.http.post(
            urlsplit(metadata["token_endpoint"]).path, data={"junk": "1"}
        )

        assert registration.status_code == 201
        assert authorize.status_code == 302
        assert login.status_code == 200
        assert (
            token.status_code == 401
        )  # invalid_client від SDK (без client_id), а не 404

    async def test_resource_guard_sees_the_prefixed_token_path(
        self, agent: Agent
    ) -> None:
        response = await agent.http.post(
            "/mcp/token", data={"resource": "https://evil.example/mcp"}
        )

        assert response.status_code == 400
        assert response.json() == {"error": "invalid_target"}

    async def test_the_mcp_endpoint_itself_is_not_shadowed_by_the_prefix(
        self, agent: Agent
    ) -> None:
        response = await agent.http.post(MCP_PATH, json={})

        assert response.status_code == 401

    async def test_a_prefix_inside_the_path_is_not_stripped(self, agent: Agent) -> None:
        response = await agent.http.get("/mcpx/login")

        assert response.status_code == 404
