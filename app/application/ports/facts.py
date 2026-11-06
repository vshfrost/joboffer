"""Порти контексту facts: репозиторії фактів і оригіналу CV та unit of work, що їх відкриває.

Факт — за номером у межах користувача (`number`); чужий і неіснуючий не відрізняються.
"""

from collections.abc import Collection
from datetime import datetime
from typing import Protocol

from application.ports.unit_of_work import UnitOfWork
from domain.facts.fact import Fact, NewFact, NewOriginalCv, OriginalCv
from domain.facts.ids import FactId
from domain.identity.ids import UserId


class FactRepository(Protocol):
    async def lock_additions(self, user_id: UserId) -> None:
        """До кінця транзакції додавання й зміни фактів цього користувача йдуть по черзі:
        пошук дубля й запис не б'ються з паралельним записом того самого тексту."""
        ...

    async def find_duplicate(self, user_id: UserId, fingerprint: str) -> int | None:
        """Номер факту з таким відбитком тексту (будь-якого виду)."""
        ...

    async def add(
        self,
        user_id: UserId,
        fact_id: FactId,
        fact: NewFact,
        now: datetime,
        number: int | None = None,
    ) -> Fact:
        """Додає факт: підтверджений лише якщо `fact.confirmed`. `number` не задано — наступний
        номер користувача (з 1); задано явно (перенос з v1) — лічильник не відстає від нього."""
        ...

    async def all(self, user_id: UserId) -> list[Fact]:
        """Усі факти користувача за номером."""
        ...

    async def get(self, user_id: UserId, number: int) -> Fact | None: ...

    async def replace(
        self, user_id: UserId, number: int, fact: NewFact, now: datetime
    ) -> Fact:
        """Змінює вид і текст; підтвердження знімається."""
        ...

    async def delete(self, user_id: UserId, number: int) -> None: ...

    async def confirm(
        self, user_id: UserId, numbers: Collection[int], now: datetime
    ) -> None: ...


class OriginalCvRepository(Protocol):
    async def get(self, user_id: UserId) -> OriginalCv | None: ...

    async def save(self, user_id: UserId, cv: NewOriginalCv, now: datetime) -> None:
        """Один оригінал на користувача: новий замінює попередній."""
        ...


class FactUnitOfWork(UnitOfWork, Protocol):
    @property
    def facts(self) -> FactRepository: ...

    @property
    def original_cvs(self) -> OriginalCvRepository: ...
