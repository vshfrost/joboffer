"""HTTP: liveness і correlation ID наскрізь через create_app."""

import re

import pytest
from fastapi.testclient import TestClient

from bootstrap.api import create_app
from bootstrap.settings import Settings
from infrastructure.http.correlation import HEADER


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(environment="test")))


def test_healthz_is_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_response_gets_generated_correlation_id(client: TestClient) -> None:
    assert re.fullmatch(r"[0-9a-f]{32}", client.get("/healthz").headers[HEADER])


def test_safe_incoming_correlation_id_is_kept(client: TestClient) -> None:
    response = client.get("/healthz", headers={HEADER: "req-42.a_b"})
    assert response.headers[HEADER] == "req-42.a_b"


@pytest.mark.parametrize(
    "unsafe", ["", "a" * 65, "with space", "bad/slash", "кирилиця", "x;drop"]
)
def test_unsafe_incoming_correlation_id_is_replaced(
    client: TestClient, unsafe: str
) -> None:
    response = client.get("/healthz", headers={HEADER.encode(): unsafe.encode()})
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers[HEADER])
