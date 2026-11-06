"""Детермінований час для тестів: жодного now() з реального годинника."""

from datetime import UTC, datetime, timedelta

DEFAULT_START = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


class FakeClock:
    """Годинник, що стоїть на місці, доки тест явно його не посуне."""

    def __init__(self, start: datetime = DEFAULT_START) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock приймає лише aware datetime (UTC)")
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> datetime:
        if delta < timedelta(0):
            raise ValueError("час не йде назад")
        self._now += delta
        return self._now
