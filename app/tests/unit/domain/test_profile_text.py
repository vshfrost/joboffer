"""Нормалізація тексту полів профілю."""

import pytest

from domain.profile.text import one_line, unique_lines


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Taras   Prykladenko ", "Taras Prykladenko"),
        ("Valencia,\n Spain", "Valencia, Spain"),
        ("   ", ""),
    ],
)
def test_one_line_collapses_whitespace(raw: str, expected: str) -> None:
    assert one_line(raw) == expected


def test_unique_lines_strips_drops_empty_and_dedupes_ignoring_case() -> None:
    items = ["  Python ", "", "python", "Go", "  ", "GO", "Rust"]
    assert unique_lines(items) == ("Python", "Go", "Rust")


def test_unique_lines_keeps_the_first_spelling_and_order() -> None:
    assert unique_lines(["b", "A", "B", "a"]) == ("b", "A")
