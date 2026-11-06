"""Altcha v1 (SHA-256): формат задачі й payload віджета, перевірка розв'язку.

Фікстура відтворює формат віджета: salt з `?expires=<unix>`, challenge = sha256(salt + number),
signature = HMAC-SHA256(ключ, challenge) у hex, payload = base64(JSON). Значення пораховані
окремо від коду (python hashlib/hmac у скрипті), не взяті з його виводу.
"""

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from domain.identity.altcha import AltchaPolicy, check_solution, make_challenge
from domain.identity.errors import AltchaFailed
from tests.support.altcha import TEST_KEY

POLICY = AltchaPolicy(key=TEST_KEY, max_number=50_000)
EXPIRES = datetime(2026, 1, 1, 9, 5, tzinfo=UTC)  # unix 1767258300
SALT = "00112233445566778899aabb?expires=1767258300"
CHALLENGE = "9d32b4043ddb6a83b6e91b325ba677f142b9f31ff7ff096f101f9925f1572e83"
SIGNATURE = "50a4381236738a419b2dd5e097ee0153ed7657ec21e35d9bd829eaa78675efc4"
NUMBER = 12345
PAYLOAD = (
    "eyJhbGdvcml0aG0iOiJTSEEtMjU2IiwiY2hhbGxlbmdlIjoiOWQzMmI0MDQzZGRiNmE4M2I2ZTkxYjMy"
    "NWJhNjc3ZjE0MmI5ZjMxZmY3ZmYwOTZmMTAxZjk5MjVmMTU3MmU4MyIsIm51bWJlciI6MTIzNDUsInNh"
    "bHQiOiIwMDExMjIzMzQ0NTU2Njc3ODg5OWFhYmI/ZXhwaXJlcz0xNzY3MjU4MzAwIiwic2lnbmF0dXJl"
    "IjoiNTBhNDM4MTIzNjczOGE0MTliMmRkNWUwOTdlZTAxNTNlZDc2NTdlYzIxZTM1ZDliZDgyOWVhYTc4"
    "Njc1ZWZjNCJ9"
)
NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def _payload(**changes: object) -> str:
    fields: dict[str, object] = {
        "algorithm": "SHA-256",
        "challenge": CHALLENGE,
        "number": NUMBER,
        "salt": SALT,
        "signature": SIGNATURE,
    }
    fields.update(changes)
    return base64.b64encode(json.dumps(fields).encode()).decode()


def test_challenge_has_widget_v1_format() -> None:
    challenge = make_challenge(
        POLICY, nonce="00112233445566778899aabb", number=NUMBER, expires_at=EXPIRES
    )
    assert (
        challenge.algorithm,
        challenge.challenge,
        challenge.maxnumber,
        challenge.salt,
        challenge.signature,
    ) == ("SHA-256", CHALLENGE, 50_000, SALT, SIGNATURE)


def test_widget_payload_is_accepted() -> None:
    solution = check_solution(POLICY, PAYLOAD, NOW)
    assert (solution.signature, solution.expires_at) == (SIGNATURE, EXPIRES)


def test_payload_is_accepted_up_to_the_expiry_moment() -> None:
    assert check_solution(POLICY, PAYLOAD, EXPIRES).signature == SIGNATURE


def test_expired_challenge_is_rejected() -> None:
    with pytest.raises(AltchaFailed):
        check_solution(POLICY, PAYLOAD, EXPIRES + timedelta(seconds=1))


def test_forged_signature_is_rejected() -> None:
    forged = SIGNATURE[:-1] + ("0" if SIGNATURE[-1] != "0" else "1")
    with pytest.raises(AltchaFailed):
        check_solution(POLICY, _payload(signature=forged), NOW)


def test_signature_made_with_another_key_is_rejected() -> None:
    other = AltchaPolicy(key="another-test-key-0123456789abcdefgh", max_number=50_000)
    with pytest.raises(AltchaFailed):
        check_solution(other, PAYLOAD, NOW)


def test_wrong_number_is_rejected() -> None:
    with pytest.raises(AltchaFailed):
        check_solution(POLICY, _payload(number=NUMBER + 1), NOW)


def test_extended_expiry_in_salt_is_rejected() -> None:
    # Строк у salt входить у challenge і підпис: подовжити його без ключа не вийде.
    with pytest.raises(AltchaFailed):
        check_solution(
            POLICY, _payload(salt="00112233445566778899aabb?expires=1867258300"), NOW
        )


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not base64 !!!",
        base64.b64encode(b"not json").decode(),
        base64.b64encode(b'["list"]').decode(),
        base64.b64encode(b"{}").decode(),
    ],
    ids=["empty", "not-base64", "not-json", "not-object", "no-fields"],
)
def test_broken_payload_is_rejected(payload: str) -> None:
    with pytest.raises(AltchaFailed):
        check_solution(POLICY, payload, NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {"algorithm": "SHA-512"},
        {"number": "12345"},
        {"number": True},
        {"number": None},
        {"signature": 5},
        {"salt": "00112233445566778899aabb"},
    ],
    ids=[
        "algorithm",
        "number-str",
        "number-bool",
        "number-null",
        "signature-int",
        "no-expires",
    ],
)
def test_payload_with_bad_field_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(AltchaFailed):
        check_solution(POLICY, _payload(**changes), NOW)


def test_signature_with_non_ascii_characters_is_rejected_as_a_failed_check() -> None:
    with pytest.raises(AltchaFailed):
        check_solution(POLICY, _payload(signature="é" * 64), NOW)
