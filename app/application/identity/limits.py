"""Ліміт «не більше N подій за вікно» поверх `SignupLimits`: ключ задає виклик (domain/identity/throttle.py)."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from application.ports.signup import SignupLimits
from domain.identity.errors import TooManyAttempts


@dataclass(frozen=True, slots=True)
class Limit:
    window: timedelta
    maximum: int
    message: str


async def ensure_below(
    limits: SignupLimits, key: str, limit: Limit, now: datetime
) -> None:
    """Подій за вікно вже `maximum` → `TooManyAttempts`. Межа вікна виключна."""
    since = now - limit.window
    recent = [at for at in await limits.since(key, since) if at > since]
    if len(recent) < limit.maximum:
        return
    # Блок знімається, коли з вікна вийде найстаріша з останніх `maximum` подій.
    unblocked_at = recent[-limit.maximum] + limit.window
    retry_after = max(1, math.ceil((unblocked_at - now).total_seconds()))
    raise TooManyAttempts(limit.message, retry_after=retry_after)
