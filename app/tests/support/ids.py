"""Детерміновані ID для тестів: UUID з лічильника замість uuid4()."""

from uuid import UUID


class SequentialIds:
    """Видає UUID(int=1), UUID(int=2), … — однаково в кожному прогоні."""

    def __init__(self, start: int = 1) -> None:
        if start < 1:
            raise ValueError("лічильник починається з 1")
        self._next = start

    def new(self) -> UUID:
        value = UUID(int=self._next)
        self._next += 1
        return value
