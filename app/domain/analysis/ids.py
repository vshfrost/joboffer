"""ID аналізу: внутрішній UUID запису. Назовні аналіз — завжди за номером вакансії."""

from dataclasses import dataclass
from typing import ClassVar

from domain.shared.ids import EntityId


@dataclass(frozen=True, slots=True)
class AnalysisId(EntityId):
    field_name: ClassVar[str] = "analysis_id"


@dataclass(frozen=True, slots=True)
class GapAnswerId(EntityId):
    field_name: ClassVar[str] = "gap_answer_id"
