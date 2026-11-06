"""Порт журналу аудиту OAuth: core не логує сам, а віддає подію адаптеру."""

from dataclasses import dataclass
from typing import Protocol

from domain.identity.ids import GrantId, UserId


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEvent:
    """Подія без секретів: ні кодів, ні токенів, ні rid. `redirect` — адреса, куди йде код."""

    name: str
    user_id: UserId | None = None
    grant_id: GrantId | None = None
    client_id: str | None = None
    client_name: str | None = None
    redirect: str | None = None


class AuditLog(Protocol):
    def record(self, event: AuditEvent) -> None: ...
