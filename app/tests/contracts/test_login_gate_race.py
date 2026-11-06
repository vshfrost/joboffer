"""Логін-гейт: запит на вхід міг застаріти між перевіркою пароля й видачею коду."""

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import httpx2
import pytest
from starlette.applications import Starlette

from application.contracts.identity import UserView
from application.contracts.oauth import PendingView
from application.identity.sessions import SessionUseCases
from application.oauth.use_cases import OAuthUseCases
from domain.identity.ids import UserId
from domain.oauth.errors import AuthorizationExpired
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


class AcceptingSessions:
    async def verify_login(self, command: object) -> UserView:
        return UserView(
            id="6f1c0a52-0000-4000-8000-000000000001",
            email="taras@example.com",
            display_name="Богдан",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


async def test_request_that_expired_during_sign_in_is_reported_as_stale() -> None:
    gate = LoginGate(
        cast(OAuthUseCases, ExpiringOAuth()),
        cast(SessionUseCases, AcceptingSessions()),
        FileTemplates.load(CATALOG),
        lambda request: "10.0.0.1",
    )
    app = Starlette()
    app.add_route("/login", gate.handle, methods=["POST"])

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.post(
            "/login",
            data={
                "rid": "r",
                "email": "taras@example.com",
                "password": "correct horse battery",
            },
        )

    assert response.status_code == 400
    assert "застарів" in response.text
    assert "location" not in response.headers
