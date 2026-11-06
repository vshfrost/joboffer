"""Сесія входу: дайджест токена, політика строків, ковзний простій і абсолютний строк.

Сам токен знає лише користувач (cookie); у домені й сховищі живе його sha256-дайджест.
Час приходить явним значенням — домен не викликає now().
"""

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Self

from domain.identity.ids import SessionId, UserId
from domain.shared.errors import InvalidValue

_DIGEST = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class TokenDigest:
    value: str

    def __post_init__(self) -> None:
        if not _DIGEST.fullmatch(self.value):
            raise InvalidValue(
                "token_digest", "Дайджест токена — 64 символи hex у нижньому регістрі"
            )

    @classmethod
    def from_token(cls, token: str) -> Self:
        return cls(hashlib.sha256(token.encode()).hexdigest())


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    """`idle` — скільки сесія живе без активності (ковзає), `absolute` — скільки загалом."""

    idle: timedelta
    absolute: timedelta

    def __post_init__(self) -> None:
        if self.idle <= timedelta(0) or self.absolute <= timedelta(0):
            raise InvalidValue("session_policy", "Строки сесії мають бути додатними")
        if self.idle > self.absolute:
            raise InvalidValue(
                "session_policy", "Простій не може бути довшим за абсолютний строк"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class Session:
    id: SessionId
    user_id: UserId
    token_digest: TokenDigest
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime

    @classmethod
    def start(
        cls,
        *,
        id: SessionId,
        user_id: UserId,
        token_digest: TokenDigest,
        now: datetime,
        policy: SessionPolicy,
    ) -> Self:
        return cls(
            id=id,
            user_id=user_id,
            token_digest=token_digest,
            created_at=now,
            last_seen_at=now,
            expires_at=now + policy.absolute,
        )

    def is_active(self, now: datetime, policy: SessionPolicy) -> bool:
        """Межі виключні: рівно в момент ліміту сесія вже закрита."""
        return now < self.expires_at and now - self.last_seen_at < policy.idle

    def seen(self, now: datetime) -> Self:
        return replace(self, last_seen_at=now)
