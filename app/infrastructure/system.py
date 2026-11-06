"""Системні адаптери портів часу й ID."""

import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class RandomIds:
    def new(self) -> UUID:
        return uuid4()


class RandomTokens:
    def new(self) -> str:
        """256 біт з CSPRNG, url-safe: ≥ 43 символи."""
        return secrets.token_urlsafe(32)


class RandomAltcha:
    def nonce(self) -> str:
        return secrets.token_hex(12)

    def number(self, max_number: int) -> int:
        return secrets.randbelow(max_number + 1)


class RandomCodes:
    def new(self) -> str:
        """Шестицифровий код із CSPRNG; ведучі нулі зберігаються."""
        return f"{secrets.randbelow(10**6):06d}"
