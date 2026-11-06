"""HTTP: помилки входу мапляться у статуси; 429 несе Retry-After."""

from typing import NoReturn

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from bootstrap.api import create_app
from bootstrap.settings import Settings
from domain.identity.errors import (
    INVALID_CREDENTIALS_MESSAGE,
    InvalidCredentials,
    NotAuthenticated,
    TooManyAttempts,
)
from domain.shared.errors import DomainError
from infrastructure.http.auth import CsrfFailed

ERRORS: dict[str, DomainError] = {
    "credentials": InvalidCredentials(INVALID_CREDENTIALS_MESSAGE),
    "anonymous": NotAuthenticated("Потрібен вхід"),
    "throttled": TooManyAttempts("Забагато спроб", retry_after=42),
    "csrf": CsrfFailed("Невірний CSRF-токен"),
}


def _raise(name: str) -> NoReturn:
    raise ERRORS[name]


@pytest.fixture
def client() -> TestClient:
    app = create_app(Settings(environment="test"))
    router = APIRouter()

    @router.get("/raise/{name}")
    async def raise_error(name: str) -> None:
        _raise(name)

    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("name", "status", "code"),
    [
        ("credentials", 401, "invalid_credentials"),
        ("anonymous", 401, "not_authenticated"),
        ("throttled", 429, "too_many_attempts"),
        ("csrf", 403, "csrf_failed"),
    ],
)
def test_auth_errors_map_to_status_and_code(
    client: TestClient, name: str, status: int, code: str
) -> None:
    response = client.get(f"/raise/{name}")
    assert (response.status_code, response.json()["code"]) == (status, code)


def test_throttling_tells_when_to_retry(client: TestClient) -> None:
    assert client.get("/raise/throttled").headers["Retry-After"] == "42"


def test_other_errors_have_no_retry_after(client: TestClient) -> None:
    assert "Retry-After" not in client.get("/raise/credentials").headers
