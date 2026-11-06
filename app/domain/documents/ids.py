"""ID документа: внутрішній UUID. Назовні документ — за номером у межах користувача (`Document.number`)."""

from dataclasses import dataclass
from typing import ClassVar

from domain.shared.ids import EntityId


@dataclass(frozen=True, slots=True)
class DocumentId(EntityId):
    field_name: ClassVar[str] = "document_id"
