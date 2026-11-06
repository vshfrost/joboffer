"""ID сутностей контексту identity."""

from dataclasses import dataclass
from typing import ClassVar

from domain.shared.ids import EntityId


@dataclass(frozen=True, slots=True)
class UserId(EntityId):
    field_name: ClassVar[str] = "user_id"


@dataclass(frozen=True, slots=True)
class GrantId(EntityId):
    field_name: ClassVar[str] = "grant_id"


@dataclass(frozen=True, slots=True)
class SessionId(EntityId):
    field_name: ClassVar[str] = "session_id"


@dataclass(frozen=True, slots=True)
class ExternalIdentityId(EntityId):
    field_name: ClassVar[str] = "external_identity_id"


@dataclass(frozen=True, slots=True)
class SignupInviteId(EntityId):
    field_name: ClassVar[str] = "signup_invite_id"


@dataclass(frozen=True, slots=True)
class SignupRequestId(EntityId):
    field_name: ClassVar[str] = "signup_id"
