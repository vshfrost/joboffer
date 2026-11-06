"""Агент користувача: застосунок (Claude, ChatGPT…), якому він дозволив доступ через OAuth."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domain.agents.ids import AgentId
from domain.identity.ids import GrantId, UserId
from domain.oauth.ids import ClientId


class AgentKind(StrEnum):
    CLAUDE = "claude"
    CLAUDE_CODE = "claude_code"
    CHATGPT = "chatgpt"
    CODEX = "codex"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    """Чим агент назвався: вид і назва для списку."""

    kind: AgentKind
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class UserAgent:
    """Один рядок на пару (користувач, OAuth-клієнт); `grant_id` — найновіший грант цього клієнта (`None`, якщо його прибрано)."""

    id: AgentId
    user_id: UserId
    client_id: ClientId
    grant_id: GrantId | None
    kind: AgentKind
    name: str
    created_at: datetime
