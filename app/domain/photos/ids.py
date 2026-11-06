"""ID фото: внутрішній UUID. Для людей і MCP є ще номер у межах користувача (`Photo.number`)."""

from dataclasses import dataclass
from typing import ClassVar

from domain.shared.ids import EntityId


@dataclass(frozen=True, slots=True)
class PhotoId(EntityId):
    field_name: ClassVar[str] = "photo_id"
