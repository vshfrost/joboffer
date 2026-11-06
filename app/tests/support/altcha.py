"""Адаптери altcha для core-тестів: детермінована випадковість і сховище в пам'яті з commit."""

import base64
import hashlib
import json
from datetime import datetime
from types import TracebackType
from typing import Self

# Очевидний тестовий ключ (≥ 32 символи), не секрет.
TEST_KEY = "test-altcha-hmac-key-0123456789abcdef"


def solve_challenge(
    *, algorithm: str, challenge: str, maxnumber: int, salt: str, signature: str
) -> str:
    """Розв'язує задачу так, як віджет: перебір 0..maxnumber; повертає base64-JSON payload."""
    number = next(
        n
        for n in range(maxnumber + 1)
        if hashlib.sha256(f"{salt}{n}".encode()).hexdigest() == challenge
    )
    fields = {
        "algorithm": algorithm,
        "challenge": challenge,
        "number": number,
        "salt": salt,
        "signature": signature,
    }
    return base64.b64encode(json.dumps(fields).encode()).decode()


class FakeAltchaRandom:
    def __init__(self, nonce: str = "00112233445566778899aabb", number: int = 12345):
        self._nonce = nonce
        self._number = number
        self.asked_max: list[int] = []

    def nonce(self) -> str:
        return self._nonce

    def number(self, max_number: int) -> int:
        self.asked_max.append(max_number)
        return self._number


class CountingAltchaRandom:
    """Кожна видана задача — з новим nonce, тож розв'язки різні (фіксований nonce дає повтор)."""

    def __init__(self, number: int = 7) -> None:
        self._number = number
        self._issued = 0

    def nonce(self) -> str:
        self._issued += 1
        return f"{self._issued:024x}"

    def number(self, max_number: int) -> int:
        return min(self._number, max_number)


class InMemorySolvedAltchas:
    def __init__(self, rows: dict[str, datetime]) -> None:
        self._rows = rows

    async def claim(self, signature: str, expires_at: datetime) -> bool:
        if signature in self._rows:
            return False
        self._rows[signature] = expires_at
        return True

    async def purge(self, now: datetime) -> None:
        for signature in [s for s, until in self._rows.items() if until < now]:
            del self._rows[signature]


class InMemoryAltchaUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(self, store: dict[str, datetime]) -> None:
        self._store = store
        self._staged: dict[str, datetime] | None = None

    @property
    def solved_altchas(self) -> InMemorySolvedAltchas:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemorySolvedAltchas(self._staged)

    async def __aenter__(self) -> Self:
        self._staged = dict(self._store)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        self._store.clear()
        self._store.update(self._staged)
