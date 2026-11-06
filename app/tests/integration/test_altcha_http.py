"""Altcha через HTTP на справжньому Postgres: видача задачі, одноразовий розв'язок, закрита реєстрація.

Реєстрації ще нема, тому перевірку розв'язку викликає пробний маршрут із тестового застосунку.
"""

import base64
import hashlib
import hmac
import json
import re
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx2
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr

from bootstrap.api import container_of, create_app
from bootstrap.settings import Settings
from tests.support.altcha import TEST_KEY

MAXNUMBER = 500

type ClientFactory = Callable[..., TestClient]


class Payload(BaseModel):
    payload: str


@pytest.fixture
def make_client(database_url: str) -> Iterator[ClientFactory]:
    opened: list[TestClient] = []

    def factory(**overrides: Any) -> TestClient:
        settings = Settings(environment="test", database_url=database_url, **overrides)
        app = create_app(settings)
        probe = APIRouter()
        altcha = container_of(app).altcha

        @probe.post("/probe-altcha", status_code=204)
        async def check(body: Payload) -> None:
            await altcha.verify(body.payload)

        app.include_router(probe)
        client = TestClient(app)
        client.__enter__()
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: ClientFactory) -> TestClient:
    return make_client(altcha_hmac_key=SecretStr(TEST_KEY), altcha_maxnumber=MAXNUMBER)


def solve(challenge: dict[str, Any]) -> str:
    """Розв'язує задачу як віджет: перебір 0..maxnumber, відповідь — base64-JSON."""
    number = next(
        n
        for n in range(challenge["maxnumber"] + 1)
        if hashlib.sha256(f"{challenge['salt']}{n}".encode()).hexdigest()
        == challenge["challenge"]
    )
    fields = {
        "algorithm": challenge["algorithm"],
        "challenge": challenge["challenge"],
        "number": number,
        "salt": challenge["salt"],
        "signature": challenge["signature"],
    }
    return base64.b64encode(json.dumps(fields).encode()).decode()


def fetch(client: TestClient) -> dict[str, Any]:
    response = client.get("/auth/challenge")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def verify(client: TestClient, payload: str) -> httpx2.Response:
    return client.post("/probe-altcha", json={"payload": payload})


def test_challenge_has_widget_v1_fields(client: TestClient) -> None:
    response = client.get("/auth/challenge")
    body = response.json()
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert sorted(body) == [
        "algorithm",
        "challenge",
        "maxnumber",
        "salt",
        "signature",
    ]
    assert (body["algorithm"], body["maxnumber"]) == ("SHA-256", MAXNUMBER)


def test_challenge_signature_is_hmac_sha256_of_challenge(client: TestClient) -> None:
    body = fetch(client)
    expected = hmac.new(TEST_KEY.encode(), body["challenge"].encode(), "sha256")
    assert body["signature"] == expected.hexdigest()


def test_challenge_salt_expires_in_five_minutes(client: TestClient) -> None:
    body = fetch(client)
    match = re.fullmatch(r"[0-9a-f]+\?expires=(\d+)", body["salt"])
    assert match is not None
    assert 295 <= int(match.group(1)) - time.time() <= 300


def test_each_challenge_is_new(client: TestClient) -> None:
    assert fetch(client)["salt"] != fetch(client)["salt"]


def test_solved_challenge_is_accepted(client: TestClient) -> None:
    assert verify(client, solve(fetch(client))).status_code == 204


def test_same_solution_second_time_is_rejected(client: TestClient) -> None:
    payload = solve(fetch(client))
    first = verify(client, payload)
    second = verify(client, payload)
    assert (first.status_code, second.status_code) == (204, 422)
    assert second.json()["code"] == "challenge_failed"


def test_used_solution_stays_rejected_after_restart(
    client: TestClient, make_client: ClientFactory
) -> None:
    payload = solve(fetch(client))
    assert verify(client, payload).status_code == 204
    restarted = make_client(
        altcha_hmac_key=SecretStr(TEST_KEY), altcha_maxnumber=MAXNUMBER
    )
    assert verify(restarted, payload).status_code == 422


def test_forged_signature_is_rejected(client: TestClient) -> None:
    challenge = fetch(client)
    challenge["signature"] = "0" * 64
    response = verify(client, solve(challenge))
    assert (response.status_code, response.json()["code"]) == (422, "challenge_failed")


def test_expired_challenge_is_rejected(client: TestClient) -> None:
    # Підписана вірним ключем, але строк минув 6 хвилин тому.
    salt = f"00112233445566778899aabb?expires={int(time.time()) - 360}"
    challenge = hashlib.sha256(f"{salt}7".encode()).hexdigest()
    signature = hmac.new(TEST_KEY.encode(), challenge.encode(), "sha256").hexdigest()
    fields = {
        "algorithm": "SHA-256",
        "challenge": challenge,
        "number": 7,
        "salt": salt,
        "signature": signature,
    }
    payload = base64.b64encode(json.dumps(fields).encode()).decode()
    response = verify(client, payload)
    assert (response.status_code, response.json()["code"]) == (422, "challenge_failed")


def test_wrong_number_is_rejected(client: TestClient) -> None:
    challenge = fetch(client)
    fields = json.loads(base64.b64decode(solve(challenge)))
    fields["number"] += 1
    payload = base64.b64encode(json.dumps(fields).encode()).decode()
    assert verify(client, payload).status_code == 422


def test_broken_payload_is_rejected(client: TestClient) -> None:
    assert verify(client, "це не base64").status_code == 422


def test_without_key_challenge_is_not_issued(make_client: ClientFactory) -> None:
    response = make_client().get("/auth/challenge")
    assert response.status_code == 503
    assert response.json()["code"] == "registration_closed"


def test_without_key_solution_is_not_accepted(
    client: TestClient, make_client: ClientFactory
) -> None:
    payload = solve(fetch(client))
    response = verify(make_client(), payload)
    assert (response.status_code, response.json()["code"]) == (
        503,
        "registration_closed",
    )
