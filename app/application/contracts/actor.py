"""Actor: хто виконує команду. Будують лише вхідні адаптери з перевіреної identity (сесія, OAuth grant).

У application немає способу зібрати Actor із тіла запиту: усі поля — типізовані значення, а не `dict`.
Перевірку credentials і scopes роблять адаптери та use cases, не цей клас.
"""

from dataclasses import dataclass
from enum import StrEnum

from domain.identity.ids import GrantId, UserId
from domain.shared.errors import InvalidValue


class Channel(StrEnum):
    WEB = "web"
    MCP = "mcp"
    CLI = "cli"


class Scope(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True, slots=True, kw_only=True)
class Actor:
    """`client_id` — непрозора мітка клієнта для історії, не авторизація; `grant_id` є лише в mcp."""

    user_id: UserId
    channel: Channel
    client_id: str
    grant_id: GrantId | None
    scopes: frozenset[Scope]
    correlation_id: str

    def __post_init__(self) -> None:
        if not self.client_id.strip():
            raise InvalidValue("client_id", "Ідентифікатор клієнта обовʼязковий")
        if not self.correlation_id.strip():
            raise InvalidValue("correlation_id", "Ідентифікатор кореляції обовʼязковий")
        if not self.scopes:
            raise InvalidValue("scopes", "Потрібен хоча б один scope")
        if self.channel is Channel.MCP and self.grant_id is None:
            raise InvalidValue("grant_id", "Для каналу mcp потрібен grant")
        if self.channel is not Channel.MCP and self.grant_id is not None:
            raise InvalidValue("grant_id", "Grant є лише в каналу mcp")
