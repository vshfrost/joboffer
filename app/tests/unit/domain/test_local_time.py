"""День за Мадридом: літній і зимовий час, перехід доби."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from domain.shared.local_time import local_day, local_today


@pytest.mark.parametrize(
    ("moment", "day"),
    [
        (datetime(2026, 1, 15, 12, 0, tzinfo=UTC), "2026-01-15"),
        (datetime(2026, 1, 15, 22, 59, tzinfo=UTC), "2026-01-15"),
        (datetime(2026, 1, 15, 23, 0, tzinfo=UTC), "2026-01-16"),
        (datetime(2026, 7, 1, 21, 59, tzinfo=UTC), "2026-07-01"),
        (datetime(2026, 7, 1, 22, 0, tzinfo=UTC), "2026-07-02"),
        (datetime(2026, 12, 31, 23, 30, tzinfo=UTC), "2027-01-01"),
    ],
)
def test_the_day_is_the_one_in_madrid(moment: datetime, day: str) -> None:
    assert local_day(moment) == day


def test_a_moment_in_another_zone_is_converted() -> None:
    moment = datetime(2026, 7, 1, 23, 30, tzinfo=timezone(timedelta(hours=-5)))
    assert local_day(moment) == "2026-07-02"


@pytest.mark.parametrize(
    ("moment", "day"),
    [
        (datetime(2026, 1, 15, 22, 59, tzinfo=UTC), date(2026, 1, 15)),
        (datetime(2026, 1, 15, 23, 0, tzinfo=UTC), date(2026, 1, 16)),
        (datetime(2026, 7, 1, 22, 0, tzinfo=UTC), date(2026, 7, 2)),
    ],
)
def test_today_is_the_calendar_day_in_madrid(moment: datetime, day: date) -> None:
    assert local_today(moment) == day
