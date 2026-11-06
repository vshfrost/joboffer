"""Порт часу: домен отримує `now` явно, а звідки він — вирішує адаптер (система чи тест)."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Aware datetime в UTC."""
        ...
