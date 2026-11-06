"""«Оновити зараз» для джерел: ліміт запитів користувача за ковзне вікно. Прогін позначає запити
виконаними, але ліміт не зменшує: вікно рахує самі запити."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from domain.shared.errors import DomainError
from domain.shared.local_time import local_time

# Не більше стількох запитів користувача за ковзне вікно.
MANUAL_REFRESH_LIMIT = 2
MANUAL_REFRESH_WINDOW = timedelta(minutes=30)


class RefreshLimit(DomainError):
    """Ліміт запитів «оновити зараз» вичерпано; next_at — коли звільниться наступний запит."""

    code = "refresh_limit"
    next_at: datetime

    def __init__(self, next_at: datetime) -> None:
        super().__init__(
            f"Оновлення джерел уже запитано {MANUAL_REFRESH_LIMIT} рази за 30 хв — "
            f"наступне о {local_time(next_at):%H:%M} (Мадрид)."
        )
        self.next_at = next_at


@dataclass(frozen=True, slots=True)
class ManualRefresh:
    """Запити «оновити зараз» користувача: скільки лишилось у вікні й коли звільниться наступний
    (None — запити є)."""

    remaining: int
    next_at: datetime | None = None


def manual_refresh(requested: Sequence[datetime], now: datetime) -> ManualRefresh:
    """Ліміт MANUAL_REFRESH_LIMIT запитів за ковзне вікно MANUAL_REFRESH_WINDOW: запит старший
    за вікно вже не рахується."""
    recent = sorted(at for at in requested if at > now - MANUAL_REFRESH_WINDOW)
    if len(recent) < MANUAL_REFRESH_LIMIT:
        return ManualRefresh(MANUAL_REFRESH_LIMIT - len(recent))
    return ManualRefresh(
        0, recent[len(recent) - MANUAL_REFRESH_LIMIT] + MANUAL_REFRESH_WINDOW
    )
