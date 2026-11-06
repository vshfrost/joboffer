"""Контракт тулів відповідей = v1: поля, типи, enum-и, межі limit і обовʼязковість схем збігаються з v1."""

from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.mail.replies import ReplyUseCases
from application.ports.prompts import PromptKey
from infrastructure.mcp.annotations import READ, WRITE
from infrastructure.mcp.tools.replies import register_reply_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.contracts.test_mcp_applications_schema import _resolve
from tests.support.clock import FakeClock
from tests.support.mail import InMemoryMailUnitOfWork, MailStore
from tests.support.v1_reply_schemas import V1

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
TOOLS = ["list_replies", "review_reply"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def agent() -> MCPServer:
    store = MailStore()
    replies = ReplyUseCases(lambda: InMemoryMailUnitOfWork(store), FakeClock())
    server = MCPServer("test")
    register_reply_tools(server, replies, FilePrompts.load(CATALOG))
    return server


async def tool_of(agent: MCPServer, name: str) -> Any:
    found = [t for t in await agent.list_tools() if t.name == name]
    assert found, f"тула {name} нема"
    return found[0]


async def test_the_server_offers_exactly_the_two_reply_tools(agent: MCPServer) -> None:
    assert sorted(t.name for t in await agent.list_tools()) == sorted(TOOLS)


@pytest.mark.parametrize("name", TOOLS)
async def test_input_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)

    resolved = _resolve(tool.input_schema, tool.input_schema.get("$defs", {}))
    assert resolved == V1[name]["in"]


@pytest.mark.parametrize("name", TOOLS)
async def test_output_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)

    assert tool.output_schema is not None
    resolved = _resolve(tool.output_schema, tool.output_schema.get("$defs", {}))
    assert resolved == V1[name]["out"]


async def test_listing_only_reads_and_reviewing_writes(agent: MCPServer) -> None:
    assert (await tool_of(agent, "list_replies")).annotations == READ
    assert (await tool_of(agent, "review_reply")).annotations == WRITE


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("list_replies", PromptKey.MCP_TOOL_LIST_REPLIES),
        ("review_reply", PromptKey.MCP_TOOL_REVIEW_REPLY),
    ],
)
async def test_the_description_comes_from_the_catalog(
    agent: MCPServer, name: str, key: PromptKey
) -> None:
    assert (await tool_of(agent, name)).description == FilePrompts.load(CATALOG).get(
        key
    )


async def test_untrusted_fields_are_named_so(agent: MCPServer) -> None:
    schema = (await tool_of(agent, "list_replies")).output_schema
    assert schema is not None
    reply_fields = schema["$defs"]["ReplyView"]["properties"]

    assert {"untrusted_from_name", "untrusted_subject", "untrusted_text"} <= set(
        reply_fields
    )
    assert "subject" not in reply_fields
    assert "text" not in reply_fields
