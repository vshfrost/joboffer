"""Порт unit of work: межа транзакції use case. Реалізація — в infrastructure (на БД чи в пам'яті)."""

from types import TracebackType
from typing import Protocol, Self


class UnitOfWork(Protocol):
    """`async with uow:` відкриває транзакцію; без `await uow.commit()` вихід усе відкочує."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...
