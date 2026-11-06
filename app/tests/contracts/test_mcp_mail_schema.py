"""Контракт тула пошти = v1: поля, типи, enum-и й обовʼязковість схем збігаються з v1."""

import re
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.mail.inbox import MailUseCases
from application.ports.prompts import PromptKey
from infrastructure.mcp.annotations import READ
from infrastructure.mcp.tools.mail import register_mail_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.contracts.test_mcp_applications_schema import _resolve
from tests.support.clock import FakeClock
from tests.support.mail import InMemoryMailUnitOfWork, MailStore
from tests.support.v1_mail_schemas import V1

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def agent() -> MCPServer:
    store = MailStore()
    mail = MailUseCases(lambda: InMemoryMailUnitOfWork(store), FakeClock(), "m@x.y")
    server = MCPServer("test")
    register_mail_tools(server, mail, FilePrompts.load(CATALOG), "http://web")
    return server


async def tool(agent: MCPServer) -> Any:
    tools = await agent.list_tools()
    assert [t.name for t in tools] == ["get_mail_inbox"]
    return tools[0]


async def test_input_schema_equals_v1(agent: MCPServer) -> None:
    found = await tool(agent)

    assert (
        _resolve(found.input_schema, found.input_schema.get("$defs", {}))
        == V1["get_mail_inbox"]["in"]
    )


async def test_output_schema_equals_v1(agent: MCPServer) -> None:
    found = await tool(agent)

    assert found.output_schema is not None
    resolved = _resolve(found.output_schema, found.output_schema.get("$defs", {}))
    assert resolved == V1["get_mail_inbox"]["out"]


async def test_the_tool_only_reads(agent: MCPServer) -> None:
    assert (await tool(agent)).annotations == READ


async def test_the_description_comes_from_the_catalog_and_names_no_person(
    agent: MCPServer,
) -> None:
    description = (await tool(agent)).description

    assert description == FilePrompts.load(CATALOG).get(
        PromptKey.MCP_TOOL_GET_MAIL_INBOX
    )
    assert not re.search(r"\b(Taras|he|his|him|himself)\b", description or "")


async def test_the_description_keeps_the_v1_meaning(agent: MCPServer) -> None:
    assert (await tool(agent)).description == (
        "The user's forwarding address for job mail, the latest Gmail forwarding "
        "confirmation code, the latest forwarded mail (sender, subject, kind, whether the "
        "sender is verified), mail dropped over the daily limit or sent to an old "
        "address, forged-sender (suspicious) mail, and the sync state. The user changes "
        "the address themself at settings_url."
    )


async def test_untrusted_fields_are_named_so(agent: MCPServer) -> None:
    schema = (await tool(agent)).output_schema
    assert schema is not None
    mail_fields = schema["$defs"]["MailView"]["properties"]

    assert {"untrusted_from_name", "untrusted_subject"} <= set(mail_fields)
    assert "subject" not in mail_fields
    assert "from_name" not in mail_fields
