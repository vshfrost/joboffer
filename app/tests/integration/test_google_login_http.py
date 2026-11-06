"""Вхід через Google у вебі наскрізь: застосунок на справжньому Postgres, Google — фейк на межі HTTP."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.identity import CreateUser
from bootstrap.api import container_of, create_app
from bootstrap.settings import Settings
from tests.support.fake_google import (
    CLIENT_ID,
    CLIENT_SECRET,
    ISSUER,
    METADATA_URL,
    FakeGoogle,
    new_key,
)

REDIRECT_URI = "https://testserver/api/auth/google/callback"
STATE_SECRET = "test-state-secret-0123456789abcdef"
PASSWORD = "correct horse battery"
SESSION_COOKIE = "__Host-joboffer_session"
STATE_COOKIE = "joboffer_oauth_state"


COUNTS = {
    "users": text("SELECT count(*) FROM users"),
    "user_identities": text("SELECT count(*) FROM user_identities"),
    "signup_requests": text("SELECT count(*) FROM signup_requests"),
}


@dataclass
class Stack:
    client: TestClient
    google: FakeGoogle
    engine: AsyncEngine
    portal: BlockingPortal

    def start(self, next_path: str | None = "/vacancies") -> tuple[str, str]:
        """Перший крок: куди веде кнопка. Повертає `state` і `nonce` із посилання на Google."""
        params = {} if next_path is None else {"next": next_path}
        response = self.client.get(
            "/auth/google/start", params=params, follow_redirects=False
        )
        assert response.status_code == 302, response.text
        query = parse_qs(urlsplit(response.headers["location"]).query)
        return query["state"][0], query["nonce"][0]

    def callback(self, state: str, **params: str) -> httpx2.Response:
        return self.client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state, **params},
            follow_redirects=False,
        )

    def sign_in(
        self, next_path: str | None = "/vacancies", **claims: Any
    ) -> httpx2.Response:
        state, nonce = self.start(next_path)
        self.google.prepare(nonce, **claims)
        return self.callback(state)

    def add_user(self, email: str = "taras@example.com") -> str:
        created = self.portal.call(
            container_of(self.client.app).identity.create_user,  # type: ignore[arg-type]
            CreateUser(email=email, display_name="Богдан", password=PASSWORD),
        )
        return created.id

    def add_signup_request(self, email: str) -> None:
        """Незавершена реєстрація: запит є, користувача ще нема."""
        insert = text(
            "INSERT INTO signup_requests (id, email, password_hash, display_name, invite_digest, terms_version,"
            " code_digest, failed_attempts, created_at, sent_at, expires_at) VALUES"
            " (gen_random_uuid(), :email, 'x', 'Богдан', 'i', '2026-10-28', 'c', 0, now(), now(), now() + interval '1 hour')"
        )

        async def run() -> None:
            async with self.engine.begin() as conn:
                await conn.execute(insert, {"email": email})

        self.portal.call(run)

    def count(self, table: str) -> int:
        query = COUNTS[table]

        async def run() -> int:
            async with self.engine.connect() as conn:
                return int((await conn.execute(query)).scalar_one())

        return self.portal.call(run)


def build(database_url: str, google: FakeGoogle, **overrides: Any) -> TestClient:
    values: dict[str, Any] = {
        "environment": "test",
        "database_url": database_url,
        "google_client_id": CLIENT_ID,
        "google_client_secret": CLIENT_SECRET,
        "google_redirect_uri": REDIRECT_URI,
        "google_metadata_url": METADATA_URL,
        "auth_state_secret": STATE_SECRET,
    } | overrides
    app = create_app(
        Settings(**values), google_transport=httpx2.ASGITransport(app=google.app())
    )
    client = TestClient(app, base_url="https://testserver")
    client.__enter__()
    return client


@pytest.fixture
def stack(
    portal: BlockingPortal, engine: AsyncEngine, database_url: str
) -> Iterator[Stack]:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
            await conn.execute(text("TRUNCATE signup_requests"))
            await conn.execute(text("TRUNCATE login_failures"))

    portal.call(clean)
    google = FakeGoogle()
    client = build(database_url, google)
    yield Stack(client, google, engine, portal)
    client.__exit__(None, None, None)


@pytest.fixture
def member(stack: Stack) -> str:
    """Користувач, який уже є в `users`: Google пускає лише таких."""
    return stack.add_user()


def assert_failed(response: httpx2.Response, error: str, stack: Stack) -> None:
    assert response.status_code == 302
    assert response.headers["location"] == f"/login?error={error}"
    assert SESSION_COOKIE not in stack.client.cookies
    assert stack.count("users") == 0 or error == "ignored"


class TestProviders:
    def test_google_is_reported_on_when_configured(self, stack: Stack) -> None:
        assert stack.client.get("/auth/providers").json() == {"google": True}

    def test_google_is_reported_off_and_the_routes_are_absent_without_configuration(
        self, database_url: str
    ) -> None:
        client = build(
            database_url,
            FakeGoogle(),
            google_client_id=None,
            google_client_secret=None,
            google_redirect_uri=None,
            auth_state_secret=None,
        )
        try:
            assert client.get("/auth/providers").json() == {"google": False}
            assert (
                client.get("/auth/google/start", follow_redirects=False).status_code
                == 404
            )
        finally:
            client.__exit__(None, None, None)


class TestStart:
    def test_start_sends_the_browser_to_google_with_state_nonce_and_pkce(
        self, stack: Stack
    ) -> None:
        response = stack.client.get(
            "/auth/google/start?next=/vacancies", follow_redirects=False
        )

        assert response.status_code == 302
        target = urlsplit(response.headers["location"])
        query = parse_qs(target.query)
        assert (
            f"{target.scheme}://{target.netloc}{target.path}" == f"{ISSUER}/authorize"
        )
        assert query["client_id"] == [CLIENT_ID]
        assert query["redirect_uri"] == [REDIRECT_URI]
        assert query["response_type"] == ["code"]
        assert set(query["scope"][0].split()) == {"openid", "email", "profile"}
        assert query["code_challenge_method"] == ["S256"]
        assert query["code_challenge"][0]
        assert query["state"][0]
        assert query["nonce"][0]

    def test_the_flow_state_lives_in_a_signed_short_lived_cookie(
        self, stack: Stack
    ) -> None:
        response = stack.client.get("/auth/google/start", follow_redirects=False)

        cookie = response.headers["set-cookie"].lower()
        assert STATE_COOKIE in cookie
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert "secure" in cookie
        assert "max-age=600" in cookie


class TestSuccess:
    def test_existing_user_with_a_verified_email_gets_the_identity_and_the_session(
        self, stack: Stack, member: str
    ) -> None:
        response = stack.sign_in("/vacancies")

        assert response.status_code == 302
        assert response.headers["location"] == "/vacancies"
        assert (stack.count("users"), stack.count("user_identities")) == (1, 1)
        me = stack.client.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["id"] == member
        assert me.json()["user"]["email"] == "taras@example.com"
        assert me.json()["csrf_token"]

    def test_the_token_request_carries_the_client_credentials_and_the_pkce_verifier(
        self, stack: Stack, member: str
    ) -> None:
        stack.sign_in()

        (request,) = stack.google.token_requests
        assert request["grant_type"] == "authorization_code"
        assert request["code"] == "auth-code"
        assert request["redirect_uri"] == REDIRECT_URI
        assert request["code_verifier"]
        assert CLIENT_SECRET in (
            request.get("client_secret"),
            request.get("basic_client_secret"),
        )

    def test_existing_email_gets_the_identity_linked_and_the_password_keeps_working(
        self, stack: Stack
    ) -> None:
        created = stack.portal.call(
            container_of(stack.client.app).identity.create_user,  # type: ignore[arg-type]
            CreateUser(
                email="taras@example.com", display_name="Богдан", password=PASSWORD
            ),
        )

        stack.sign_in()

        assert (stack.count("users"), stack.count("user_identities")) == (1, 1)
        me = stack.client.get("/auth/me").json()
        assert me["user"]["id"] == created.id
        stack.client.cookies.clear()
        login = stack.client.post(
            "/auth/login", json={"email": "taras@example.com", "password": PASSWORD}
        )
        assert login.status_code == 200

    def test_known_sub_with_a_changed_email_is_the_same_user(
        self, stack: Stack, member: str
    ) -> None:
        stack.sign_in()
        first = stack.client.get("/auth/me").json()["user"]["id"]
        stack.client.cookies.clear()

        stack.sign_in(email="new-address@example.com")

        assert stack.client.get("/auth/me").json()["user"]["id"] == first
        assert stack.count("users") == 1

    @pytest.mark.parametrize("unsafe", ["//evil", "https://evil.example", "/login"])
    def test_unsafe_next_goes_to_the_home_page(
        self, stack: Stack, member: str, unsafe: str
    ) -> None:
        response = stack.sign_in(unsafe)

        assert response.headers["location"] == "/"

    def test_without_next_it_goes_to_the_home_page(
        self, stack: Stack, member: str
    ) -> None:
        assert stack.sign_in(None).headers["location"] == "/"

    def test_the_flow_state_cookie_is_spent_after_a_successful_sign_in(
        self, stack: Stack, member: str
    ) -> None:
        state, nonce = stack.start()
        stack.google.prepare(nonce)
        assert stack.callback(state).status_code == 302

        replay = stack.callback(state)

        assert replay.headers["location"] == "/login?error=invalid_state"


class TestRefusals:
    @pytest.mark.parametrize(
        "claims",
        [
            {"email": None},
            {"email_verified": False},
            {"email_verified": None},
            {"email": "not-an-email"},
        ],
    )
    def test_no_usable_verified_email_means_no_user_no_identity_and_no_session(
        self, stack: Stack, claims: dict[str, Any]
    ) -> None:
        response = stack.sign_in(**claims)

        assert_failed(response, "email_required", stack)
        assert stack.count("user_identities") == 0

    def test_email_absent_from_users_is_refused_like_a_missing_email_and_creates_nothing(
        self, stack: Stack
    ) -> None:
        response = stack.sign_in(email="stranger@example.com")

        assert_failed(response, "email_required", stack)
        assert (stack.count("users"), stack.count("user_identities")) == (0, 0)

    def test_email_that_is_only_in_an_unfinished_signup_is_refused_and_creates_nothing(
        self, stack: Stack
    ) -> None:
        stack.add_signup_request("taras@example.com")

        response = stack.sign_in()

        assert_failed(response, "email_required", stack)
        assert (stack.count("users"), stack.count("user_identities")) == (0, 0)
        assert stack.count("signup_requests") == 1

    def test_unverified_email_of_a_password_user_is_not_linked(
        self, stack: Stack
    ) -> None:
        stack.portal.call(
            container_of(stack.client.app).identity.create_user,  # type: ignore[arg-type]
            CreateUser(
                email="taras@example.com", display_name="Богдан", password=PASSWORD
            ),
        )

        response = stack.sign_in(email_verified=False)

        assert response.headers["location"] == "/login?error=email_required"
        assert SESSION_COOKIE not in stack.client.cookies
        assert stack.count("user_identities") == 0

    def test_wrong_state_is_refused(self, stack: Stack) -> None:
        _, nonce = stack.start()
        stack.google.prepare(nonce)

        response = stack.callback("not-the-state")

        assert_failed(response, "invalid_state", stack)
        assert stack.google.token_requests == []

    def test_callback_without_a_started_flow_is_refused(self, stack: Stack) -> None:
        stack.google.prepare("n")

        assert_failed(stack.callback("any-state"), "invalid_state", stack)

    def test_wrong_nonce_is_refused(self, stack: Stack) -> None:
        state, _ = stack.start()
        stack.google.prepare("a-different-nonce")

        assert_failed(stack.callback(state), "failed", stack)

    def test_id_token_signed_with_another_key_is_refused(self, stack: Stack) -> None:
        state, nonce = stack.start()
        stack.google.prepare(nonce, key=new_key())

        assert_failed(stack.callback(state), "failed", stack)

    @pytest.mark.parametrize(
        "claims",
        [
            {"aud": "someone-elses-client-id"},
            {"iss": "https://evil.example"},
            {"exp": 1_000_000_000},
            {"sub": None},
        ],
    )
    def test_id_token_with_wrong_audience_issuer_expiry_or_no_subject_is_refused(
        self, stack: Stack, claims: dict[str, Any]
    ) -> None:
        state, nonce = stack.start()
        stack.google.prepare(nonce, **claims)

        assert_failed(stack.callback(state), "failed", stack)

    def test_the_user_denying_access_at_google_is_a_cancellation(
        self, stack: Stack
    ) -> None:
        state, _ = stack.start()

        response = stack.client.get(
            "/auth/google/callback",
            params={"error": "access_denied", "state": state},
            follow_redirects=False,
        )

        assert_failed(response, "cancelled", stack)

    def test_any_other_error_from_google_is_a_failure(self, stack: Stack) -> None:
        state, _ = stack.start()

        response = stack.client.get(
            "/auth/google/callback",
            params={"error": "server_error", "state": state},
            follow_redirects=False,
        )

        assert_failed(response, "failed", stack)

    def test_google_token_endpoint_failing_is_a_failure(self, stack: Stack) -> None:
        state, nonce = stack.start()
        stack.google.prepare(nonce)
        stack.google.token_status = 500

        assert_failed(stack.callback(state), "failed", stack)


class TestPasswordForm:
    def test_password_login_still_works_when_google_is_configured(
        self, stack: Stack
    ) -> None:
        stack.portal.call(
            container_of(stack.client.app).identity.create_user,  # type: ignore[arg-type]
            CreateUser(
                email="katya@example.com", display_name="Наталя", password=PASSWORD
            ),
        )

        response = stack.client.post(
            "/auth/login", json={"email": "katya@example.com", "password": PASSWORD}
        )

        assert response.status_code == 200
