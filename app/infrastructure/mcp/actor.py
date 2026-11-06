"""Actor тулів MCP із перевіреного токена: спільна залежність для всіх тулів."""

from uuid import uuid4

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver.exceptions import ToolError

from application.contracts.actor import Actor, Channel, Scope
from domain.identity.ids import GrantId, UserId
from domain.oauth.rules import SCOPE
from domain.shared.errors import InvalidValue


def actor_from_token(token: AccessToken, correlation_id: str) -> Actor:
    """Токен виданий нашим провайдером: `subject` — user_id, `claims.grant_id` — грант, scope — рівно `joboffer`.

    Інакше — `InvalidValue`. Scope `joboffer` дає `read` і `write`.
    """
    if token.scopes != [SCOPE]:
        raise InvalidValue("scopes", "Токен має мати рівно scope joboffer")
    return Actor(
        user_id=UserId.parse(token.subject or ""),
        channel=Channel.MCP,
        client_id=token.client_id,
        grant_id=GrantId.parse(str((token.claims or {}).get("grant_id", ""))),
        scopes=frozenset(Scope),
        correlation_id=correlation_id,
    )


def current_actor() -> Actor:
    """Actor поточного виклику тулу; кожен виклик має свій correlation_id."""
    token = get_access_token()
    if token is None:
        raise ToolError("Потрібна авторизація.")
    return actor_from_token(token, uuid4().hex)
