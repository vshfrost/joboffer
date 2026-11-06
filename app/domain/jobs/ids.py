"""ID вакансії: внутрішній UUID. Для людей і MCP є ще номер у межах користувача (`Job.number`)."""

from dataclasses import dataclass
from typing import ClassVar

from domain.shared.ids import EntityId


@dataclass(frozen=True, slots=True)
class JobId(EntityId):
    field_name: ClassVar[str] = "job_id"
