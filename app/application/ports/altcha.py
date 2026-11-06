"""Порти altcha: випадковість задачі й сховище використаних розв'язків."""

from datetime import datetime
from typing import Protocol

from application.ports.unit_of_work import UnitOfWork


class AltchaRandom(Protocol):
    def nonce(self) -> str:
        """Випадковий hex-префікс солі."""
        ...

    def number(self, max_number: int) -> int:
        """Секретне число з 0..max_number включно."""
        ...


class SolvedAltchas(Protocol):
    async def claim(self, signature: str, expires_at: datetime) -> bool:
        """Позначає розв'язок використаним; `False`, якщо його вже використано."""
        ...

    async def purge(self, now: datetime) -> None:
        """Забуває розв'язки, чий строк минув."""
        ...


class AltchaUnitOfWork(UnitOfWork, Protocol):
    @property
    def solved_altchas(self) -> SolvedAltchas: ...
