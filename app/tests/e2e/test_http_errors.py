"""HTTP: мапінг помилок. Тестові маршрути кидають помилки так, як кидали б use cases."""

from typing import ClassVar, NoReturn

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from bootstrap.api import create_app
from bootstrap.settings import Settings
from domain.shared.errors import (
    Conflict,
    DomainError,
    Forbidden,
    InvalidValue,
    NotFound,
    StaleVersion,
)
from infrastructure.http.correlation import HEADER
from infrastructure.http.errors import INTERNAL_MESSAGE, NOT_FOUND_MESSAGE


class QuotaExceeded(Conflict):
    code: ClassVar[str] = "quota_exceeded"


class Unclassified(DomainError):
    code: ClassVar[str] = "unclassified"


ERRORS: dict[str, DomainError] = {
    "missing": NotFound("Нотатки 7 нема в базі"),
    "foreign": NotFound("Нотатка 7 належить іншому користувачу"),
    "forbidden": Forbidden("Лише власник може це зробити"),
    "conflict": Conflict("Стан не дозволяє"),
    "quota": QuotaExceeded("Ліміт вичерпано"),
    "stale": StaleVersion(expected=1, actual=2),
    "invalid": InvalidValue("title", "Назва порожня"),
    "unclassified": Unclassified("Щось доменне"),
}


def _raise(name: str) -> NoReturn:
    raise ERRORS[name]


@pytest.fixture
def client() -> TestClient:
    app = create_app(Settings(environment="test"))
    router = APIRouter()

    @router.get("/raise/{name}")
    async def raise_domain(name: str) -> None:
        _raise(name)

    @router.get("/count")
    async def count(n: int) -> int:
        return n

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("SELECT secret FROM users — не має потрапити у відповідь")

    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("name", "status", "code"),
    [
        ("missing", 404, "not_found"),
        ("forbidden", 403, "forbidden"),
        ("conflict", 409, "conflict"),
        ("quota", 409, "quota_exceeded"),
        ("stale", 409, "stale_version"),
        ("invalid", 422, "invalid_value"),
        ("unclassified", 400, "unclassified"),
    ],
)
def test_domain_errors_map_to_status_and_code(
    client: TestClient, name: str, status: int, code: str
) -> None:
    response = client.get(f"/raise/{name}")
    body = response.json()
    assert (response.status_code, body["code"]) == (status, code)
    assert set(body) == {"code", "message", "field_errors", "correlation_id"}
    assert body["correlation_id"] == response.headers[HEADER]


def test_foreign_and_missing_are_indistinguishable(client: TestClient) -> None:
    headers = {HEADER: "same"}
    missing = client.get("/raise/missing", headers=headers)
    foreign = client.get("/raise/foreign", headers=headers)
    assert missing.status_code == foreign.status_code == 404
    assert missing.json() == foreign.json()
    assert missing.json()["message"] == NOT_FOUND_MESSAGE


def test_invalid_value_names_the_field(client: TestClient) -> None:
    body = client.get("/raise/invalid").json()
    assert body["field_errors"] == [{"field": "title", "message": "Назва порожня"}]


def test_request_validation_uses_same_body(client: TestClient) -> None:
    response = client.get("/count", params={"n": "abc"})
    body = response.json()
    assert (response.status_code, body["code"]) == (422, "invalid_request")
    assert [error["field"] for error in body["field_errors"]] == ["n"]


def test_unexpected_error_hides_details(client: TestClient) -> None:
    response = client.get("/boom")
    body = response.json()
    assert (response.status_code, body["code"]) == (500, "internal_error")
    assert body["message"] == INTERNAL_MESSAGE
    assert "SELECT" not in response.text
    assert "Traceback" not in response.text
