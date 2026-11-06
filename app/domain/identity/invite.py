"""Одноразове запрошення на реєстрацію: живе 7 днів, погашається один раз.

Сам токен знає лише отримувач посилання; у домені й сховищі живе його sha256-дайджест.
Час приходить явним значенням — домен не викликає now().
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Self

from domain.identity.ids import SignupInviteId
from domain.identity.session import TokenDigest

INVITE_TTL = timedelta(days=7)


@dataclass(frozen=True, slots=True, kw_only=True)
class SignupInvite:
    id: SignupInviteId
    token_digest: TokenDigest
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None

    @classmethod
    def issue(
        cls, *, id: SignupInviteId, token_digest: TokenDigest, now: datetime
    ) -> Self:
        return cls(
            id=id,
            token_digest=token_digest,
            created_at=now,
            expires_at=now + INVITE_TTL,
            used_at=None,
        )

    def is_usable(self, now: datetime) -> bool:
        """Межа виключна: рівно в момент `expires_at` запрошення вже прострочене."""
        return self.used_at is None and now < self.expires_at
