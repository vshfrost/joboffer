"""ID сутностей контексту agents."""

from dataclasses import dataclass
from typing import ClassVar

from domain.shared.ids import EntityId


@dataclass(frozen=True, slots=True)
class AgentId(EntityId):
    field_name: ClassVar[str] = "agent_id"
