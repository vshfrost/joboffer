"""ID сутностей контексту oauth. `GrantId` живе в `domain.identity.ids` (його знає `Actor`)."""

from dataclasses import dataclass
from typing import ClassVar

from domain.shared.ids import EntityId


@dataclass(frozen=True, slots=True)
class ClientId(EntityId):
    field_name: ClassVar[str] = "client_id"
