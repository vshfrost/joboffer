"""Збирач помилок полів: розбір розділу повідомляє про всі проблеми, а не лише про першу."""

from domain.shared.errors import FieldProblem, InvalidFields


class Problems:
    def __init__(self) -> None:
        self._found: list[FieldProblem] = []

    def add(self, field: str, message: str) -> None:
        """На одне поле — одна помилка (перша): наступні лише повторюють суть."""
        if all(problem.field != field for problem in self._found):
            self._found.append(FieldProblem(field, message))

    def raise_if_any(self) -> None:
        if self._found:
            raise InvalidFields(self._found)
