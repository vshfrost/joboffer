"""Ізоляція core-тестів: мережа й файлова система під час тесту заборонені.

Domain і application не мають IO, тож core-тест, що відкрив файл чи сокет, — це
дефект у тесті або в коді. Захист діє лише під час виконання тесту: збирання тестів
(імпорт модулів, читання .feature) іде до нього.
"""

import builtins
import io
import os
import socket
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import NoReturn

import pytest


class CoreIsolationError(AssertionError):
    """Core-тест спробував IO."""


def _deny(what: str) -> Callable[..., NoReturn]:
    def blocked(*_args: object, **_kwargs: object) -> NoReturn:
        raise CoreIsolationError(f"core-тест не може використовувати {what}")

    return blocked


@contextmanager
def deny_io(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(builtins, "open", _deny("файлову систему (open)"))
    monkeypatch.setattr(io, "open", _deny("файлову систему (io.open)"))
    monkeypatch.setattr(os, "open", _deny("файлову систему (os.open)"))
    monkeypatch.setattr(socket.socket, "connect", _deny("мережу (socket.connect)"))
    monkeypatch.setattr(socket, "create_connection", _deny("мережу"))
    monkeypatch.setattr(socket, "getaddrinfo", _deny("мережу (DNS)"))
    yield
