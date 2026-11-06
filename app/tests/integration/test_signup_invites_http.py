"""GET /auth/signup/invite наскрізь: застосунок на справжньому Postgres, без сесії."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bootstrap.api import container_of, create_app
from bootstrap.settings import Settings

type ClientFactory = Callable[..., TestClient]

URL = "/auth/signup/invite"


@pytest.fixture
def make_client(
    portal: BlockingPortal, engine: AsyncEngine, database_url: str
) -> Iterator[ClientFactory]:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE signup_invites"))
            await conn.execute(text("TRUNCATE login_failures"))

    portal.call(clean)
    opened: list[TestClient] = []

    def factory(**overrides: Any) -> TestClient:
        settings = Settings(environment="test", database_url=database_url, **overrides)
        client = TestClient(create_app(settings), base_url="https://testserver")
        client.__enter__()
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: ClientFactory) -> TestClient:
    return make_client(signup_mode="invite")


def issue(client: TestClient) -> str:
    invites = container_of(client.app).invites  # type: ignore[arg-type]
    assert client.portal is not None
    return client.portal.call(invites.create).token


def set_expiry(portal: BlockingPortal, engine: AsyncEngine, delta: timedelta) -> None:
    async def run() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE signup_invites SET expires_at = :at"),
                {"at": datetime.now(UTC) + delta},
            )

    portal.call(run)


def test_valid_invite_is_200_with_expiry_in_seven_days(client: TestClient) -> None:
    token = issue(client)
    response = client.get(URL, params={"invite": token})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    expires = datetime.fromisoformat(body["expires_at"])
    assert abs(expires - (datetime.now(UTC) + timedelta(days=7))) < timedelta(minutes=5)


def test_check_needs_no_session_and_is_not_cached(client: TestClient) -> None:
    response = client.get(URL, params={"invite": issue(client)})
    assert (response.status_code, response.json()["valid"]) == (200, True)
    assert response.headers["cache-control"] == "no-store"


def test_unknown_expired_and_used_invites_look_the_same(
    client: TestClient, portal: BlockingPortal, engine: AsyncEngine
) -> None:
    unknown = client.get(URL, params={"invite": "token-unknown"})
    expired_token = issue(client)
    set_expiry(portal, engine, timedelta(minutes=-1))
    expired = client.get(URL, params={"invite": expired_token})
    used_token = issue(client)
    set_expiry(portal, engine, timedelta(days=1))
    assert client.portal is not None
    client.portal.call(container_of(client.app).invites.redeem, used_token)  # type: ignore[arg-type]
    used = client.get(URL, params={"invite": used_token})

    for response in (unknown, expired, used):
        assert response.status_code == 404
        assert response.json()["code"] == "invite_invalid"
    assert (
        unknown.json()["message"] == expired.json()["message"] == used.json()["message"]
    )


def test_missing_invite_parameter_is_invite_invalid(client: TestClient) -> None:
    response = client.get(URL)
    assert (response.status_code, response.json()["code"]) == (404, "invite_invalid")


def test_closed_signup_is_404_signup_closed_by_default(
    make_client: ClientFactory,
) -> None:
    client = make_client()
    token = issue(client)
    response = client.get(URL, params={"invite": token})
    assert (response.status_code, response.json()["code"]) == (404, "signup_closed")


def test_twenty_first_check_in_fifteen_minutes_is_429_with_retry_after(
    client: TestClient,
) -> None:
    for _ in range(20):
        assert client.get(URL, params={"invite": "token-unknown"}).status_code == 404
    blocked = client.get(URL, params={"invite": issue(client)})
    assert (blocked.status_code, blocked.json()["code"]) == (429, "too_many_attempts")
    assert 0 < int(blocked.headers["Retry-After"]) <= 15 * 60


def test_behind_a_trusted_proxy_each_client_has_its_own_check_limit(
    make_client: ClientFactory,
) -> None:
    client = make_client(signup_mode="invite", trusted_proxies=1)
    token = issue(client)
    for _ in range(20):
        client.get(
            URL, params={"invite": token}, headers={"X-Forwarded-For": "1.1.1.1"}
        )
    blocked = client.get(
        URL, params={"invite": token}, headers={"X-Forwarded-For": "1.1.1.1"}
    )
    other = client.get(
        URL, params={"invite": token}, headers={"X-Forwarded-For": "2.2.2.2"}
    )
    assert blocked.status_code == 429
    assert other.status_code == 200
