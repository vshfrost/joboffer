"""Помилки фактів."""

from domain.shared.errors import Conflict


class DuplicateFact(Conflict):
    """Такий текст уже є в іншому факті користувача (`number` — його номер)."""

    code = "duplicate_fact"

    def __init__(self, number: int) -> None:
        super().__init__(f"Такий факт уже є: #{number}.")
        self.number = number
