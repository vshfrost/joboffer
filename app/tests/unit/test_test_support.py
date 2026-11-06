"""Тестові допоміжники самі мають працювати так, як обіцяють."""

import socket
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from anyio.from_thread import BlockingPortal
from anyio.lowlevel import checkpoint

from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.isolation import CoreIsolationError


def test_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="aware"):
        FakeClock(datetime(2026, 1, 1))  # noqa: DTZ001 — навмисно naive


def test_clock_does_not_go_back(clock: FakeClock) -> None:
    with pytest.raises(ValueError, match="назад"):
        clock.advance(timedelta(seconds=-1))


def test_ids_start_from_one() -> None:
    with pytest.raises(ValueError, match="з 1"):
        SequentialIds(start=0)


def test_fixtures_are_fresh_per_test(clock: FakeClock, ids: SequentialIds) -> None:
    # Інший тест уже рухав годинник і брав ID — тут стан знову початковий.
    assert clock.now().isoformat() == "2026-01-01T09:00:00+00:00"
    assert ids.new().int == 1


def _connect_raw_socket() -> None:
    with socket.socket() as sock:
        sock.connect(("127.0.0.1", 9))


@pytest.mark.parametrize(
    "action",
    [
        lambda: open("/etc/hosts"),  # noqa: SIM115, PTH123 — перевіряємо саме builtins.open
        lambda: Path("/etc/hosts").read_text(),
        lambda: socket.create_connection(("example.com", 80)),
        _connect_raw_socket,
        lambda: socket.getaddrinfo("example.com", 80),
    ],
    ids=["open", "path_read", "create_connection", "socket.connect", "dns"],
)
def test_core_tests_cannot_do_io(action: Callable[[], object]) -> None:
    with pytest.raises(CoreIsolationError):
        action()


def test_portal_runs_async_code_under_io_guard(portal: BlockingPortal) -> None:
    async def double(value: int) -> int:
        await checkpoint()
        return value * 2

    assert portal.call(double, 21) == 42
