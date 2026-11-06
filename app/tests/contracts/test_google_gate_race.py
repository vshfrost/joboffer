"""Гейт Google: запит на вхід міг застаріти, поки користувач був у Google."""

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import httpx2
import pytest
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware

from application.contracts.identity import GoogleClaims, UserView
from application.contracts.oauth import PendingView
from application.identity.sessions import SessionUseCases
from application.identity.use_cases import IdentityUseCases
from application.oauth.use_cases import OAuthUseCases
from domain.identity.ids import UserId
from domain.oauth.errors import AuthorizationExpired
from infrastructure.http.google import GoogleLogin
from infrastructure.mcp.google_gate import GoogleGate
from infrastructure.mcp.login_gate import LoginGate
from infrastructure.templates.catalog import FileTemplates

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "templates"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class ExpiringOAuth:
    async def describe_pending(self, rid: str) -> PendingView | None:
        return PendingView(client_name="Claude", redirect_host="claude.ai")

    async def complete_authorization(self, rid: str, user_id: UserId) -> object:
        raise AuthorizationExpired("застарів")


class VerifiedGoogle:
    async def claims(self, request: object) -> GoogleClaims:
        return GoogleClaims(
            subject="s", email="taras@example.com", email_verified=True, name="Богдан"
        )


class KnownUser:
    async def sign_in_with_google(self, claims: GoogleClaims) -> UserView:
        return UserView(
            id="6f1c0a52-0000-4000-8000-000000000001",
            email="taras@example.com",
            display_name="Богдан",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


async def test_request_that_expired_during_the_google_round_trip_is_stale() -> None:
    oauth = cast(OAuthUseCases, ExpiringOAuth())
    login_gate = LoginGate(
        oauth,
        cast(SessionUseCases, object()),
        FileTemplates.load(CATALOG),
        lambda request: "10.0.0.1",
    )
    gate = GoogleGate(
        cast(GoogleLogin, VerifiedGoogle()),
        login_gate,
        oauth,
        cast(IdentityUseCases, KnownUser()),
    )
    app = Starlette()
    app.add_route("/callback", gate.callback, methods=["GET"])
    app.add_middleware(
        SessionMiddleware, secret_key="test-state-secret-0123456789abcdef"
    )

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.get("/callback", params={"code": "c", "state": "s"})

    assert response.status_code == 400
    assert "застарів" in response.text
    assert "location" not in response.headers
