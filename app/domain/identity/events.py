"""Події користувача (стаб для red-коміту)."""

from dataclasses import dataclass

from domain.identity.ids import UserId
from domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class UserRegisteredEvent(DomainEvent):
    user_id: UserId
    version: int
