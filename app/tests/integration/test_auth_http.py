"""Вхід через HTTP наскрізь: cookie-сесія, CSRF, ліміт спроб, Actor — застосунок на справжньому Postgres."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.actor import Actor
from application.contracts.identity import CreateUser
from bootstrap.api import container_of, create_app
from bootstrap.settings import Settings
from infrastructure.http.auth import CSRF_HEADER
from infrastructure.http.correlation import HEADER as CORRELATION_HEADER

PASSWORD = "correct horse battery"
OTHER_PASSWORD = "another long password"
COOKIE = "__Host-joboffer_session"

type ClientFactory = Callable[..., TestClient]


@pytest.fixture
def make_client(
    portal: BlockingPortal, engine: AsyncEngine, database_url: str
) -> Iterator[ClientFactory]:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
            await conn.execute(text("TRUNCATE login_failures"))

    portal.call(clean)
    opened: list[TestClient] = []

    def factory(peer: str = "testclient", **overrides: Any) -> TestClient:
        settings = Settings(environment="test", database_url=database_url, **overrides)
        app = create_app(settings)
        probe = APIRouter()

        @probe.get("/probe")
        @probe.post("/probe")
        async def whoami(
            actor: Actor = Depends(container_of(app).auth.actor),  # noqa: B008
        ) -> dict[str, Any]:
            return {
                "user_id": str(actor.user_id),
                "channel": actor.channel.value,
                "client_id": actor.client_id,
                "grant_id": actor.grant_id,
                "scopes": sorted(scope.value for scope in actor.scopes),
                "correlation_id": actor.correlation_id,
            }

        app.include_router(probe)
        # https: Secure-cookie не відправляється по http, а клієнт імітує браузер.
        client = TestClient(app, base_url="https://testserver", client=(peer, 50000))
        client.__enter__()  # lifespan закриває engine при виході
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


def add_user(
    client: TestClient, email: str, name: str, password: str = PASSWORD
) -> None:
    identity = container_of(client.app).identity  # type: ignore[arg-type]
    command = CreateUser(email=email, display_name=name, password=password)
    assert client.portal is not None
    client.portal.call(identity.create_user, command)


@pytest.fixture
def client(make_client: ClientFactory) -> TestClient:
    client = make_client()
    add_user(client, "taras@example.com", "Богдан")
    return client


def login(
    client: TestClient,
    email: str = "taras@example.com",
    password: str = PASSWORD,
    **headers: str,
) -> httpx2.Response:
    return client.post(
        "/auth/login", json={"email": email, "password": password}, headers=headers
    )


def csrf_of(response: httpx2.Response) -> str:
    return str(response.json()["csrf_token"])


def test_login_returns_user_and_csrf_token(client: TestClient) -> None:
    response = login(client)
    body = response.json()
    assert response.status_code == 200
    assert body["user"]["email"] == "taras@example.com"
    assert body["user"]["display_name"] == "Богдан"
    assert body["csrf_token"]
    assert PASSWORD not in response.text
    assert "hash" not in response.text.lower()


def test_login_sets_a_hardened_cookie(client: TestClient) -> None:
    cookie = login(client).headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=")
    assert len(cookie.split(";")[0].split("=", 1)[1]) >= 32
    for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert attribute in cookie
    assert f"Max-Age={30 * 24 * 3600}" in cookie


def test_cookie_is_not_marked_secure_when_configured_off(
    make_client: ClientFactory,
) -> None:
    client = make_client(cookie_secure=False)
    add_user(client, "taras@example.com", "Богдан")
    assert "Secure" not in login(client).headers["set-cookie"]


def test_session_cookie_is_host_prefixed_and_has_no_domain(
    client: TestClient,
) -> None:
    cookie = login(client).headers["set-cookie"]
    assert cookie.startswith("__Host-joboffer_session=")
    assert "Domain" not in cookie
    assert "Path=/" in cookie
    assert "Secure" in cookie


def test_dev_over_http_keeps_the_plain_cookie_name(
    make_client: ClientFactory,
) -> None:
    client = make_client(cookie_secure=False)
    add_user(client, "taras@example.com", "Богдан")
    assert login(client).headers["set-cookie"].startswith("joboffer_session=")


def test_auth_responses_are_not_cached(client: TestClient) -> None:
    assert login(client).headers["cache-control"] == "no-store"
    assert client.get("/auth/me").headers["cache-control"] == "no-store"


def test_me_returns_the_user_and_the_same_csrf_token(client: TestClient) -> None:
    issued = login(client)
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["user"] == issued.json()["user"]
    assert csrf_of(me) == csrf_of(issued)


def test_me_without_cookie_is_401(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert (response.status_code, response.json()["code"]) == (401, "not_authenticated")


def test_me_with_garbage_cookie_is_401(client: TestClient) -> None:
    client.cookies.set(COOKIE, "garbage")
    assert client.get("/auth/me").status_code == 401


def test_wrong_password_and_unknown_email_look_the_same(client: TestClient) -> None:
    wrong = login(client, password="wrong password 123")
    unknown = login(client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["code"] == unknown.json()["code"] == "invalid_credentials"
    assert wrong.json()["message"] == unknown.json()["message"]
    assert "set-cookie" not in wrong.headers


def test_login_with_missing_fields_is_422(client: TestClient) -> None:
    response = client.post("/auth/login", json={"email": "taras@example.com"})
    assert (response.status_code, response.json()["code"]) == (422, "invalid_request")


def test_sixth_login_after_five_failures_is_429_even_with_the_right_password(
    client: TestClient,
) -> None:
    for _ in range(5):
        assert login(client, password="wrong password 123").status_code == 401
    blocked = login(client)
    assert (blocked.status_code, blocked.json()["code"]) == (429, "too_many_attempts")
    assert int(blocked.headers["Retry-After"]) > 0


def test_forged_forwarded_header_does_not_bypass_the_limit_by_default(
    client: TestClient,
) -> None:
    for number in range(5):
        login(
            client,
            password="wrong password 123",
            **{"X-Forwarded-For": f"9.9.9.{number}"},
        )
    blocked = login(client, **{"X-Forwarded-For": "8.8.8.8"})
    assert blocked.status_code == 429


def test_behind_a_trusted_proxy_each_client_has_its_own_limit(
    make_client: ClientFactory,
) -> None:
    client = make_client(trusted_proxies=1)
    add_user(client, "taras@example.com", "Богдан")
    for _ in range(5):
        login(client, password="wrong password 123", **{"X-Forwarded-For": "1.1.1.1"})
    assert login(client, **{"X-Forwarded-For": "1.1.1.1"}).status_code == 429
    assert login(client, **{"X-Forwarded-For": "2.2.2.2"}).status_code == 200


def test_trusted_proxy_uses_the_entry_added_by_the_proxy_not_the_client(
    make_client: ClientFactory,
) -> None:
    # Клієнт може дописати лівий запис; довіряємо лише останньому (його додав наш проксі).
    client = make_client(trusted_proxies=1)
    add_user(client, "taras@example.com", "Богдан")
    for number in range(5):
        login(
            client,
            password="wrong password 123",
            **{"X-Forwarded-For": f"6.6.6.{number}, 1.1.1.1"},
        )
    assert login(client, **{"X-Forwarded-For": "7.7.7.7, 1.1.1.1"}).status_code == 429


def fail_five_times(client: TestClient, **headers: str) -> None:
    for _ in range(5):
        login(client, password="wrong password 123", **headers)


def test_cloudflare_header_from_a_local_proxy_gives_each_client_its_own_limit(
    make_client: ClientFactory,
) -> None:
    client = make_client(peer="127.0.0.1", client_ip_header="cf-connecting-ip")
    add_user(client, "taras@example.com", "Богдан")
    fail_five_times(client, **{"CF-Connecting-IP": "203.0.113.1"})
    assert login(client, **{"CF-Connecting-IP": "203.0.113.1"}).status_code == 429
    assert login(client, **{"CF-Connecting-IP": "203.0.113.2"}).status_code == 200


def test_forged_cloudflare_header_from_a_public_peer_is_ignored(
    make_client: ClientFactory,
) -> None:
    client = make_client(peer="93.184.216.34", client_ip_header="cf-connecting-ip")
    add_user(client, "taras@example.com", "Богдан")
    for number in range(5):
        login(
            client,
            password="wrong password 123",
            **{"CF-Connecting-IP": f"203.0.113.{number}"},
        )
    assert login(client, **{"CF-Connecting-IP": "203.0.113.99"}).status_code == 429


def test_cloudflare_header_is_ignored_when_not_configured(
    make_client: ClientFactory,
) -> None:
    client = make_client(peer="127.0.0.1")
    add_user(client, "taras@example.com", "Богдан")
    for number in range(5):
        login(
            client,
            password="wrong password 123",
            **{"CF-Connecting-IP": f"203.0.113.{number}"},
        )
    assert login(client, **{"CF-Connecting-IP": "203.0.113.99"}).status_code == 429


def test_logout_without_csrf_token_is_403_and_keeps_the_session(
    client: TestClient,
) -> None:
    login(client)
    response = client.post("/auth/logout")
    assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")
    assert client.get("/auth/me").status_code == 200


def test_logout_with_wrong_csrf_token_is_403(client: TestClient) -> None:
    login(client)
    response = client.post("/auth/logout", headers={CSRF_HEADER: "wrong"})
    assert response.status_code == 403


def test_logout_closes_the_session_and_the_old_cookie_stops_working(
    client: TestClient,
) -> None:
    issued = login(client)
    old_cookie = client.cookies[COOKIE]
    response = client.post("/auth/logout", headers={CSRF_HEADER: csrf_of(issued)})
    assert response.status_code == 204
    assert f"{COOKIE}=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    client.cookies.clear()
    client.cookies.set(COOKIE, old_cookie)
    assert client.get("/auth/me").status_code == 401


def test_logout_without_a_session_is_a_noop_204(client: TestClient) -> None:
    assert client.post("/auth/logout").status_code == 204


def test_csrf_token_of_another_session_is_rejected(make_client: ClientFactory) -> None:
    client = make_client()
    add_user(client, "taras@example.com", "Богдан")
    add_user(client, "katya@example.com", "Наталя", OTHER_PASSWORD)
    katya_csrf = csrf_of(login(client, "katya@example.com", OTHER_PASSWORD))
    client.cookies.clear()
    login(client)
    response = client.post("/auth/logout", headers={CSRF_HEADER: katya_csrf})
    assert response.status_code == 403


def test_each_session_sees_its_own_user(make_client: ClientFactory) -> None:
    client = make_client()
    add_user(client, "taras@example.com", "Богдан")
    add_user(client, "katya@example.com", "Наталя", OTHER_PASSWORD)
    login(client)
    taras_cookie = client.cookies[COOKIE]
    client.cookies.clear()
    login(client, "katya@example.com", OTHER_PASSWORD)
    assert client.get("/auth/me").json()["user"]["email"] == "katya@example.com"
    client.cookies.clear()
    client.cookies.set(COOKIE, taras_cookie)
    assert client.get("/auth/me").json()["user"]["email"] == "taras@example.com"


def test_session_past_its_absolute_expiry_is_401(
    portal: BlockingPortal, engine: AsyncEngine, client: TestClient
) -> None:
    login(client)

    async def expire() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE sessions SET expires_at = :at"),
                {"at": datetime.now(UTC) - timedelta(minutes=1)},
            )

    portal.call(expire)
    assert client.get("/auth/me").status_code == 401


def test_session_idle_longer_than_the_limit_is_401(
    portal: BlockingPortal, engine: AsyncEngine, client: TestClient
) -> None:
    login(client)

    async def make_idle() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE sessions SET last_seen_at = :at"),
                {"at": datetime.now(UTC) - timedelta(hours=13)},
            )

    portal.call(make_idle)
    assert client.get("/auth/me").status_code == 401


def test_database_keeps_only_the_token_digest(
    portal: BlockingPortal, engine: AsyncEngine, client: TestClient
) -> None:
    login(client)
    token = client.cookies[COOKIE]

    async def stored() -> list[str]:
        async with engine.connect() as conn:
            rows = await conn.execute(text("SELECT token_digest FROM sessions"))
            return [str(value) for value in rows.scalars()]

    (digest,) = portal.call(stored)
    assert token != digest
    assert token not in digest
    assert len(digest) == 64


def test_actor_comes_from_the_session(client: TestClient) -> None:
    issued = login(client)
    response = client.get("/probe", headers={CORRELATION_HEADER: "req-42"})
    assert response.json() == {
        "user_id": issued.json()["user"]["id"],
        "channel": "web",
        "client_id": "web",
        "grant_id": None,
        "scopes": ["read", "write"],
        "correlation_id": "req-42",
    }


def test_actor_requires_a_session(client: TestClient) -> None:
    response = client.get("/probe")
    assert (response.status_code, response.json()["code"]) == (401, "not_authenticated")


def test_actor_on_unsafe_methods_requires_the_csrf_token(client: TestClient) -> None:
    issued = login(client)
    rejected = client.post("/probe")
    assert (rejected.status_code, rejected.json()["code"]) == (403, "csrf_failed")
    accepted = client.post("/probe", headers={CSRF_HEADER: csrf_of(issued)})
    assert accepted.status_code == 200
