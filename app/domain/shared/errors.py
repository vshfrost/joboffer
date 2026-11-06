"""Помилки домену: стабільний код для мапінгу назовні, повідомлення українською, без HTTP."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar


class DomainError(Exception):
    """База. `code` — стабільний ідентифікатор категорії; кожен підклас задає свій."""

    code: ClassVar[str]

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidValue(DomainError):
    """Значення поля не проходить інваріант (формат, межі, дозволений набір)."""

    code = "invalid_value"

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


class Conflict(DomainError):
    """Операція суперечить поточному стану (версія, ліміт). Конкретні випадки — підкласи зі своїм кодом."""

    code = "conflict"


class StaleVersion(Conflict):
    """Автор правки бачив застарілу версію: хтось змінив запис раніше."""

    code = "stale_version"

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            f"Запис уже змінено: очікувана версія {expected}, поточна {actual}"
        )
        self.expected = expected
        self.actual = actual


class NotFound(DomainError):
    """Сутності нема або вона недоступна цьому користувачу. Однакова відповідь не розкриває, що існує."""

    code = "not_found"


class Forbidden(DomainError):
    """Користувач бачить сутність, але ця дія йому недоступна."""

    code = "forbidden"


@dataclass(frozen=True, slots=True)
class FieldProblem:
    """Одна помилка поля: `field` — шлях до поля (`locations.2.place`)."""

    field: str
    message: str


class InvalidFields(InvalidValue):
    """Кілька помилок полів разом: форма показує кожну біля свого поля, а не лише першу."""

    code = "invalid_fields"

    def __init__(self, problems: Sequence[FieldProblem]) -> None:
        super().__init__(problems[0].field, " ".join(p.message for p in problems))
        self.problems = tuple(problems)
