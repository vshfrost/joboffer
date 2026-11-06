"""HTTP: помилки реєстрації мапляться у статуси й коди; невдалий код несе кількість спроб."""

from typing import NoReturn

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from bootstrap.api import create_app
from bootstrap.settings import Settings
from domain.identity.errors import (
    AltchaFailed,
    CodeIncorrect,
    InviteAlreadyUsed,
    PasswordWeak,
    SignupExpired,
    SignupMailUnavailable,
)
from domain.shared.errors import DomainError

ERRORS: dict[str, DomainError] = {
    "challenge": AltchaFailed("Перевірку не пройдено"),
    "weak": PasswordWeak("Додай до пароля: цифру"),
    "expired": SignupExpired("Запит недійсний"),
    "code": CodeIncorrect("Невірний код", attempts_left=3),
    "used": InviteAlreadyUsed("Запрошення вже використано"),
    "mail": SignupMailUnavailable("Лист не надіслано"),
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
        ("challenge", 422, "challenge_failed"),
        ("weak", 422, "password_weak"),
        ("expired", 422, "signup_expired"),
        ("code", 422, "code_incorrect"),
        ("used", 409, "invite_used"),
        ("mail", 503, "mail_unavailable"),
    ],
)
def test_signup_errors_map_to_status_and_code(
    client: TestClient, name: str, status: int, code: str
) -> None:
    response = client.get(f"/raise/{name}")
    assert (response.status_code, response.json()["code"]) == (status, code)


def test_a_wrong_code_response_carries_the_attempts_left_and_the_field() -> None:
    app = create_app(Settings(environment="test"))
    router = APIRouter()

    @router.get("/raise")
    async def raise_error() -> None:
        raise CodeIncorrect("Невірний код", attempts_left=3)

    app.include_router(router)
    body = TestClient(app, raise_server_exceptions=False).get("/raise").json()

    assert body.get("attempts_left") == 3
    assert [e["field"] for e in body["field_errors"]] == ["code"]


def test_other_errors_have_no_attempts_left(client: TestClient) -> None:
    assert "attempts_left" not in client.get("/raise/expired").json()
