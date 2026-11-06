"""ID джерела користувача: компанії ATS чи RSS-стрічки (UUID; номерів у джерел нема)."""

from dataclasses import dataclass
from typing import ClassVar

from domain.shared.ids import EntityId


@dataclass(frozen=True, slots=True)
class SourceId(EntityId):
    field_name: ClassVar[str] = "source_id"
