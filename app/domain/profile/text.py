"""Нормалізація тексту полів профілю."""

from collections.abc import Iterable


def one_line(text: str) -> str:
    """Один рядок: пробіли й переноси всередині стискаються до одного пробілу, краї обрізаються."""
    return " ".join(text.split())


def unique_lines(items: Iterable[str]) -> tuple[str, ...]:
    """Елементи без пробілів по краях, без порожніх і без повторів (без урахування регістру).

    Порядок першої появи зберігається.
    """
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        item = raw.strip()
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            result.append(item)
    return tuple(result)
