"""Тул `get_cv_funnel`: звіт воронки за версіями CV. Без параметрів, лише читає; опис — з каталогу
і пояснює Claude, що таке відповідь, інтервʼю і «unknown»."""

import re
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.applications.use_cases import ApplicationUseCases
from application.ports.prompts import PromptKey
from infrastructure.mcp.annotations import READ
from infrastructure.mcp.tools.funnel import register_funnel_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.support.applications import InMemoryApplicationUnitOfWork
from tests.support.clock import FakeClock
from tests.support.jobs import Store

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"


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
    register_funnel_tools(server, applications, FilePrompts.load(CATALOG))
    return server


async def funnel_tool(agent: MCPServer) -> Any:
    (tool,) = await agent.list_tools()
    return tool


async def test_the_server_offers_one_read_only_tool_without_parameters(
    agent: MCPServer,
) -> None:
    tool = await funnel_tool(agent)

    assert tool.name == "get_cv_funnel"
    assert tool.input_schema.get("properties", {}) == {}
    assert tool.annotations == READ


async def test_the_report_has_one_row_per_cv_version_with_the_three_counts(
    agent: MCPServer,
) -> None:
    schema = (await funnel_tool(agent)).output_schema

    row = schema["$defs"]["CvFunnelRowView"]
    assert set(schema["properties"]) == {"versions"}
    assert set(row["properties"]) == {
        "cv_number",
        "cv_date",
        "coverage_percent",
        "applications",
        "replies",
        "interviews",
    }
    assert set(row["required"]) == set(row["properties"])


async def test_the_description_comes_from_the_catalog(agent: MCPServer) -> None:
    prompts = FilePrompts.load(CATALOG)

    assert (await funnel_tool(agent)).description == prompts.get(
        PromptKey.MCP_TOOL_GET_CV_FUNNEL
    )


async def test_the_description_tells_what_counts_as_a_reply_an_interview_and_unknown(
    agent: MCPServer,
) -> None:
    description = (await funnel_tool(agent)).description or ""

    assert "replies (status replied, interview or offer)" in description
    assert "interviews (status interview or offer)" in description
    assert '"unknown"' in description
    assert not re.search(r"\b(Taras|he|his|him|himself)\b", description)
