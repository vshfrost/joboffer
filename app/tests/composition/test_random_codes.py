"""Генератор кодів підтвердження: шість цифр із CSPRNG, ведучі нулі зберігаються."""

import re

import pytest

from infrastructure.system import RandomCodes


def test_a_code_is_exactly_six_digits() -> None:
    codes = RandomCodes()

    assert all(re.fullmatch(r"\d{6}", codes.new()) for _ in range(200))


def test_codes_differ_from_call_to_call() -> None:
    codes = RandomCodes()

    assert len({codes.new() for _ in range(50)}) > 40


def test_a_small_number_keeps_its_leading_zeros(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[int] = []

    def fake_randbelow(limit: int) -> int:
        asked.append(limit)
        return 42

    monkeypatch.setattr("infrastructure.system.secrets.randbelow", fake_randbelow)

    assert RandomCodes().new() == "000042"
    assert asked == [1_000_000]
