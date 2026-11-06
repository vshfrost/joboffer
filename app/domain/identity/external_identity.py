"""Звʼязок користувача із зовнішнім провайдером входу (Google): `provider` + `subject` унікальні разом."""

from dataclasses import dataclass
from datetime import datetime

from domain.identity.ids import ExternalIdentityId, UserId

GOOGLE = "google"


@dataclass(frozen=True, slots=True, kw_only=True)
class ExternalIdentity:
    id: ExternalIdentityId
    provider: str
    subject: str
    user_id: UserId
    created_at: datetime
