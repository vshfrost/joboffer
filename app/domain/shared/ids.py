"""База typed ID: незмінна обгортка над UUID. Генерує ID зовнішній порт, не домен."""

from dataclasses import dataclass
from typing import ClassVar, Self
from uuid import UUID

from domain.shared.errors import InvalidValue

_NOT_CANONICAL = (
    "Ідентифікатор має бути UUID у канонічному записі "
    "(xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx, нижній регістр)"
)


@dataclass(frozen=True, slots=True)
class EntityId:
    """Різні типи ID з однаковим UUID не рівні: `GrantId(u) != UserId(u)`."""

    value: UUID

    # Ім'я поля в InvalidValue; кожен конкретний ID задає своє.
    field_name: ClassVar[str] = "id"

    def __post_init__(self) -> None:
        if self.value.int == 0:
            raise InvalidValue(
                self.field_name, "Ідентифікатор не може бути нульовим UUID"
            )

    @classmethod
    def parse(cls, raw: str) -> Self:
        """Приймає лише канонічний запис (нижній регістр, дефіси) і відкидає nil."""
        try:
            parsed = UUID(raw)
        except ValueError:
            raise InvalidValue(cls.field_name, _NOT_CANONICAL) from None
        if str(parsed) != raw:
            raise InvalidValue(cls.field_name, _NOT_CANONICAL)
        return cls(parsed)

    def __str__(self) -> str:
        return str(self.value)
