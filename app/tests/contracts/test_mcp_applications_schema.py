"""Контракт тулів подач = v1: поля, типи, enum-и й обовʼязковість схем збігаються з v1.

Різниць зі схемами v1 нема. Будь-яка розбіжність — помилка тесту.
"""

import re
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.applications.use_cases import ApplicationUseCases
from application.ports.prompts import PromptKey
from infrastructure.mcp.annotations import WRITE
from infrastructure.mcp.tools.applications import register_application_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.support.applications import InMemoryApplicationUnitOfWork
from tests.support.clock import FakeClock
from tests.support.jobs import Store
from tests.support.v1_application_schemas import V1

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
TOOLS = ["mark_applied", "set_application_status"]


def _resolve(node: Any, defs: dict[str, Any]) -> Any:
    """Розгортає `$ref` і прибирає title / description / default: порівнюється форма, а не оздоблення."""
    if isinstance(node, list):
        return [_resolve(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        return _resolve(defs[node["$ref"].rsplit("/", 1)[1]], defs)
    result: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties":
            result[key] = {name: _resolve(s, defs) for name, s in value.items()}
        elif key not in {"title", "description", "default", "$defs"}:
            result[key] = _resolve(value, defs)
    return result


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def agent() -> MCPServer:
    store = Store.empty()
    applications = ApplicationUseCases(
        lambda: InMemoryApplicationUnitOfWork(store), FakeClock()
    )
    server = MCPServer("test")
    register_application_tools(server, applications, FilePrompts.load(CATALOG))
    return server


async def tool_of(agent: MCPServer, name: str) -> Any:
    return next(t for t in await agent.list_tools() if t.name == name)


async def test_the_server_offers_exactly_the_two_application_tools(
    agent: MCPServer,
) -> None:
    assert sorted(t.name for t in await agent.list_tools()) == sorted(TOOLS)


@pytest.mark.parametrize("name", TOOLS)
async def test_input_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    assert (
        _resolve(tool.input_schema, tool.input_schema.get("$defs", {}))
        == V1[name]["in"]
    )


@pytest.mark.parametrize("name", TOOLS)
async def test_output_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    output = tool.output_schema
    assert output is not None
    assert _resolve(output, output.get("$defs", {})) == V1[name]["out"]


async def test_field_descriptions_say_the_v1_things(agent: MCPServer) -> None:
    mark = await tool_of(agent, "mark_applied")
    application = mark.input_schema["$defs"]["ApplicationIn"]["properties"]
    assert application["applied_on"]["description"] == (
        "YYYY-MM-DD; empty: today (Europe/Madrid)"
    )
    assert application["ats"]["description"] == (
        "ATS platform the application went through"
    )
    assert application["company_domains"]["description"] == (
        "The company's own email domains, e.g. acme.com (not the ATS's)"
    )
    assert application["company_emails"]["description"] == (
        "Recruiters' addresses the user knows"
    )
    view = mark.output_schema["properties"]
    assert view["applied_on"]["description"] == "YYYY-MM-DD"
    assert view["status_changed"]["description"] == "YYYY-MM-DD"
    assert view["company_domains"]["description"] == (
        "The company's email domains: replies from them match this job"
    )


async def test_descriptions_come_from_the_catalog_and_name_no_person(
    agent: MCPServer,
) -> None:
    prompts = FilePrompts.load(CATALOG)
    described = {t.name: t.description for t in await agent.list_tools()}
    assert described == {
        "mark_applied": prompts.get(PromptKey.MCP_TOOL_MARK_APPLIED),
        "set_application_status": prompts.get(
            PromptKey.MCP_TOOL_SET_APPLICATION_STATUS
        ),
    }
    for description in described.values():
        assert not re.search(r"\b(Taras|he|his|him|himself)\b", description or "")


async def test_the_descriptions_keep_the_v1_meaning(agent: MCPServer) -> None:
    mark = (await tool_of(agent, "mark_applied")).description
    move = (await tool_of(agent, "set_application_status")).description
    assert mark == (
        "Record that the user applied to a saved job (status applied). Calling it again "
        "replaces the details and keeps the status. Company domains and addresses let "
        "joboffer match the company's replies in the user's forwarded mail: ask the "
        "user for them when unsure."
    )
    assert move == (
        "Move the user's application along: applied → replied → interview → offer; "
        "rejected or withdrawn close it. Only forward moves; the same status changes "
        "nothing."
    )


async def test_the_side_effect_hints_are_write_for_both(agent: MCPServer) -> None:
    hints = {t.name: t.annotations for t in await agent.list_tools()}
    assert hints == {"mark_applied": WRITE, "set_application_status": WRITE}
