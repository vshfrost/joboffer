"""ID факту: внутрішній UUID. Для людей і MCP є ще номер у межах користувача (`Fact.number`)."""

from dataclasses import dataclass
from typing import ClassVar

from domain.shared.ids import EntityId


@dataclass(frozen=True, slots=True)
class FactId(EntityId):
    field_name: ClassVar[str] = "fact_id"
