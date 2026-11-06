"""Теми підготовки підключено в composition root і в MCP-агента."""

import pytest
from mcp.server.mcpserver import MCPServer

from application.prep.use_cases import PrepUseCases
from bootstrap.container import build_container
from bootstrap.settings import Settings
from bootstrap.tools import register_tools


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Engine лінивий: адреса потрібна налаштуванням, сама база — ні.
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )


def test_the_container_has_prep_use_cases() -> None:
    container = build_container(Settings(environment="test"))
    assert isinstance(container.prep, PrepUseCases)


@pytest.mark.anyio
async def test_the_agent_offers_the_three_prep_tools() -> None:
    server = MCPServer("test")
    register_tools(server, build_container(Settings(environment="test")))
    names = {tool.name for tool in await server.list_tools()}
    assert {"prepare_prep_topics", "save_prep_topics", "list_prep_topics"} <= names
