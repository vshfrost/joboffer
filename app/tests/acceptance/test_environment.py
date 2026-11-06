"""Кроки для features/test_environment.feature."""

from datetime import datetime, timedelta
from uuid import UUID

from anyio.from_thread import BlockingPortal
from anyio.lowlevel import checkpoint
from pytest_bdd import given, parsers, scenarios, then, when

from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds

scenarios("features/test_environment.feature")


@given(parsers.parse('годинник показує "{moment}"'))
def clock_shows(clock: FakeClock, moment: str) -> None:
    assert clock.now() == datetime.fromisoformat(moment)


@when(parsers.parse("минає {minutes:d} хвилин"))
def time_passes(clock: FakeClock, minutes: int) -> None:
    clock.advance(timedelta(minutes=minutes))


@then(parsers.parse('годинник показує "{moment}"'))
def clock_now_is(clock: FakeClock, moment: str) -> None:
    assert clock.now() == datetime.fromisoformat(moment)


@when(parsers.parse("тест бере {count:d} нових ID"), target_fixture="taken")
def take_ids(ids: SequentialIds, count: int) -> list[UUID]:
    return [ids.new() for _ in range(count)]


@then(parsers.parse("це UUID з номерами {numbers}"))
def ids_are(taken: list[UUID], numbers: str) -> None:
    assert taken == [UUID(int=int(n)) for n in numbers.split(", ")]


@when(
    parsers.parse("асинхронна функція рахує суму {left:d} і {right:d}"),
    target_fixture="total",
)
def async_sum(portal: BlockingPortal, left: int, right: int) -> int:
    async def add() -> int:
        await checkpoint()  # справжня точка перемикання event loop
        return left + right

    return portal.call(add)


@then(parsers.parse("крок отримує {expected:d}"))
def step_gets(total: int, expected: int) -> None:
    assert total == expected
