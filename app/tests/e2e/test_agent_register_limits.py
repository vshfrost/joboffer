"""`/register` агента наскрізь: ліміти діють на обох адресах (корінь і під /mcp) ще до бази."""

import pytest
from starlette.testclient import TestClient

from bootstrap.agent import create_agent_app
from bootstrap.settings import Settings

OVERSIZE = b"x" * 20_000


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_agent_app(Settings(environment="test")))


@pytest.mark.parametrize("path", ["/register", "/mcp/register"])
def test_oversize_registration_body_is_413(client: TestClient, path: str) -> None:
    assert client.post(path, content=OVERSIZE).status_code == 413


def test_registration_flood_from_one_client_is_429_across_both_addresses(
    client: TestClient,
) -> None:
    for number in range(10):
        path = "/register" if number % 2 else "/mcp/register"
        assert client.post(path, content=OVERSIZE).status_code == 413

    response = client.post("/register", content=OVERSIZE)

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
