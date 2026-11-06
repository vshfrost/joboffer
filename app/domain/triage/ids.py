"""ID тріажу: внутрішній UUID запису. Назовні тріаж — завжди за номером вакансії."""

from dataclasses import dataclass
from typing import ClassVar

from domain.shared.ids import EntityId


@dataclass(frozen=True, slots=True)
class TriageId(EntityId):
    field_name: ClassVar[str] = "triage_id"
