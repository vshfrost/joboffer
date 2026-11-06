"""ASGI-застосунок агента (MCP для Claude). Окремий процес і порт від вебу:
назовні виставляється лише він, веб лишається у внутрішній мережі.

Запуск: `uvicorn --factory bootstrap.agent:create_agent_app`.
Маршрути OAuth (/authorize, /token, /register, /login, метадані) лежать у корені процесу:
edge (Caddy, Tunnel, Vite) веде `/mcp*` і `/.well-known/oauth-*` на агента без зміни шляху; MCP-ендпоінт —
`<origin вебу>/mcp`, OAuth-маршрути лежать і в корені процесу, і під `/mcp/…` (так їх оголошують метадані).
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import httpx2
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Route

from application.ports.prompts import PromptKey
from bootstrap.container import Container, build_container
from bootstrap.settings import MCP_PATH, Settings
from bootstrap.tools import register_tools
from domain.oauth.rules import SCOPE
from infrastructure.mcp.google_gate import GoogleGate
from infrastructure.mcp.health import healthz
from infrastructure.mcp.login_gate import LoginGate
from infrastructure.mcp.prefix import StripPrefix
from infrastructure.mcp.provider import JobofferOAuthProvider
from infrastructure.mcp.resource_guard import ResourceGuard

GATE_STATE_COOKIE = "joboffer_gate_state"
GATE_STATE_SALT = "agent-gate"
GATE_STATE_MAX_AGE = 600


def create_agent_app(
    settings: Settings | None = None,
    *,
    tools: Callable[[MCPServer, Container], None] | None = None,
    google_transport: httpx2.AsyncBaseTransport | None = None,
) -> Starlette:
    """`tools` реєструє тули на сервері до збирання застосунку; без нього — бізнес-тули застосунку."""
    container = build_container(
        settings if settings is not None else Settings(),
        google_transport=google_transport,
    )
    config = container.settings
    provider = JobofferOAuthProvider(
        container.oauth, resource_url=config.agent_public_url
    )
    agent = MCPServer(
        "joboffer",
        instructions=container.prompts.get(PromptKey.MCP_INSTRUCTIONS),
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=config.agent_public_url,
            resource_server_url=config.agent_public_url,
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]
            ),
            required_scopes=[SCOPE],
            validate_token_resource=True,
        ),
    )
    (tools or register_tools)(agent, container)
    app = agent.streamable_http_app(
        streamable_http_path=MCP_PATH,
        # Без Origin (Claude, Claude Code) — дозволено; браузерні Origin — ні.
        transport_security=TransportSecuritySettings(
            allowed_hosts=list(config.agent_allowed_hosts), allowed_origins=[]
        ),
    )
    google = container.google_gate
    gate = LoginGate(
        container.oauth,
        container.sessions,
        container.templates,
        container.auth.client_key,
        google_enabled=google is not None,
    )
    _add_issuer_metadata_route(app)
    app.add_route("/login", gate.handle, methods=["GET", "POST"])
    if google is not None:
        google_gate = GoogleGate(google, gate, container.oauth, container.identity)
        app.add_route("/auth/google/start", google_gate.start, methods=["GET"])
        app.add_route("/auth/google/callback", google_gate.callback, methods=["GET"])
        # Стан флоу гейта — своя cookie й свій підпис: стан веб-флоу тут не діє (і навпаки).
        app.add_middleware(
            SessionMiddleware,
            secret_key=f"{google.config.state_secret}:{GATE_STATE_SALT}",
            session_cookie=GATE_STATE_COOKIE,
            max_age=GATE_STATE_MAX_AGE,
            same_site="lax",
            https_only=container.settings.cookie_secure,
        )
    app.add_route("/healthz", healthz(container.engine), methods=["GET"])
    app.add_middleware(ResourceGuard, resource=config.agent_public_url)
    # Останнім = найзовнішнім: гард і маршрути бачать шлях уже без префікса.
    app.add_middleware(StripPrefix, prefix=MCP_PATH)
    app.router.lifespan_context = _lifespan(app, container)
    app.state.container = container
    return app


def _add_issuer_metadata_route(app: Starlette) -> None:
    """RFC 8414 для issuer із шляхом: клієнт шукає `/.well-known/oauth-authorization-server/mcp`, а SDK
    віддає лише кореневий документ — той самий, тож підʼєднуємо його й за шляхом issuer."""
    root = "/.well-known/oauth-authorization-server"
    route = next(r for r in app.routes if isinstance(r, Route) and r.path == root)
    app.add_route(f"{root}{MCP_PATH}", route.endpoint, methods=["GET", "OPTIONS"])


def _lifespan(
    app: Starlette, container: Container
) -> Callable[[Starlette], AbstractAsyncContextManager[None]]:
    mcp_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(asgi_app: Starlette) -> AsyncIterator[None]:
        await container.oauth.purge_expired()
        async with mcp_lifespan(asgi_app):
            yield
        await container.engine.dispose()

    return lifespan
