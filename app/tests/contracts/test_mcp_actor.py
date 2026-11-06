"""Actor тулів MCP із перевіреного токена: хто, через який канал, у межах якого гранту."""

from uuid import UUID

import pytest
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver.exceptions import ToolError

from application.contracts.actor import Actor, Channel, Scope
from domain.identity.ids import GrantId, UserId
from domain.shared.errors import InvalidValue
from infrastructure.mcp.actor import actor_from_token, current_actor

USER = UserId(UUID(int=7))
GRANT = GrantId(UUID(int=9))


def token(**overrides: object) -> AccessToken:
    values: dict[str, object] = {
        "token": "t",
        "client_id": "6f1c0a52-0000-4000-8000-000000000001",
        "scopes": ["joboffer"],
        "expires_at": 4_000_000_000,
        "resource": "https://agent.example/joboffer",
        "subject": str(USER),
        "claims": {"grant_id": str(GRANT)},
    }
    return AccessToken.model_validate(values | overrides)


def test_token_becomes_an_mcp_actor_with_read_and_write() -> None:
    actor = actor_from_token(token(), "corr-1")

    assert actor == Actor(
        user_id=USER,
        channel=Channel.MCP,
        client_id="6f1c0a52-0000-4000-8000-000000000001",
        grant_id=GRANT,
        scopes=frozenset({Scope.READ, Scope.WRITE}),
        correlation_id="corr-1",
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"subject": None},
        {"subject": "not-a-uuid"},
        {"claims": None},
        {"claims": {}},
        {"claims": {"grant_id": "not-a-uuid"}},
        {"scopes": ["admin"]},
        {"scopes": []},
    ],
)
def test_token_that_is_not_ours_is_not_an_actor(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidValue):
        actor_from_token(token(**overrides), "corr-1")


def test_calling_a_tool_without_a_verified_token_is_refused() -> None:
    with pytest.raises(ToolError):
        current_actor()
