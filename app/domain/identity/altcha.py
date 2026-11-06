"""Proof-of-work для реєстрації, формат віджета altcha v1 (SHA-256, HMAC-SHA256, лише stdlib).

Задача: `salt` = випадковий префікс + `?expires=<unix>`, `challenge` = sha256(salt + число),
`signature` = HMAC(ключ, challenge). Клієнт перебирає число 0..maxnumber і шле base64-JSON
`{algorithm, challenge, number, salt, signature}`. Строк і число захищені підписом.
"""

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from domain.identity.errors import AltchaFailed

ALGORITHM = "SHA-256"
CHALLENGE_TTL = timedelta(minutes=5)
KEY_MIN = 32
REJECTED_MESSAGE = "Перевірку не пройдено"
_EXPIRES = re.compile(r"\?expires=(\d{1,12})\Z")


@dataclass(frozen=True, slots=True)
class AltchaPolicy:
    key: str
    max_number: int


@dataclass(frozen=True, slots=True)
class AltchaChallenge:
    algorithm: str
    challenge: str
    maxnumber: int
    salt: str
    signature: str


@dataclass(frozen=True, slots=True)
class AltchaSolution:
    signature: str
    expires_at: datetime


def _challenge_of(salt: str, number: int) -> str:
    return hashlib.sha256(f"{salt}{number}".encode()).hexdigest()


def _sign(policy: AltchaPolicy, challenge: str) -> str:
    return hmac.new(policy.key.encode(), challenge.encode(), hashlib.sha256).hexdigest()


def make_challenge(
    policy: AltchaPolicy, *, nonce: str, number: int, expires_at: datetime
) -> AltchaChallenge:
    salt = f"{nonce}?expires={int(expires_at.timestamp())}"
    challenge = _challenge_of(salt, number)
    return AltchaChallenge(
        algorithm=ALGORITHM,
        challenge=challenge,
        maxnumber=policy.max_number,
        salt=salt,
        signature=_sign(policy, challenge),
    )


def _same(supplied: str, expected: str) -> bool:
    # compare_digest падає на рядках не-ASCII, а `supplied` приходить від клієнта: порівнюємо байти.
    return hmac.compare_digest(supplied.encode(), expected.encode())


def _fields(payload: str) -> dict[str, object]:
    try:
        decoded = json.loads(base64.b64decode(payload, validate=True))
    except binascii.Error, ValueError:
        raise AltchaFailed(REJECTED_MESSAGE) from None
    if not isinstance(decoded, dict):
        raise AltchaFailed(REJECTED_MESSAGE)
    return decoded


def check_solution(policy: AltchaPolicy, payload: str, now: datetime) -> AltchaSolution:
    """Невірний підпис, прострочена задача, хибне число чи зламаний payload — `AltchaFailed`."""
    fields = _fields(payload)
    algorithm, challenge, number, salt, signature = (
        fields.get(name)
        for name in ("algorithm", "challenge", "number", "salt", "signature")
    )
    if (
        algorithm != ALGORITHM
        or not isinstance(challenge, str)
        or not isinstance(number, int)
        or isinstance(number, bool)
        or not isinstance(salt, str)
        or not isinstance(signature, str)
    ):
        raise AltchaFailed(REJECTED_MESSAGE)
    if not _same(signature, _sign(policy, challenge)):
        raise AltchaFailed(REJECTED_MESSAGE)
    if not _same(challenge, _challenge_of(salt, number)):
        raise AltchaFailed(REJECTED_MESSAGE)
    match = _EXPIRES.search(salt)
    if match is None:
        raise AltchaFailed(REJECTED_MESSAGE)
    expires_at = datetime.fromtimestamp(int(match.group(1)), UTC)
    if now > expires_at:
        raise AltchaFailed(REJECTED_MESSAGE)
    return AltchaSolution(signature=signature, expires_at=expires_at)
