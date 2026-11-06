"""Контракт `answer_gap`: назва, параметри, опис із каталогу, підказка про побічні ефекти."""

import re
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.analysis.use_cases import AnalysisUseCases
from application.ports.prompts import PromptKey
from infrastructure.mcp.annotations import WRITE
from infrastructure.mcp.tools.gaps import register_gap_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.support.analysis import InMemoryAnalysisUnitOfWork
from tests.support.clock import FakeClock
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import Store

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def agent() -> MCPServer:
    prompts = FilePrompts.load(CATALOG)
    analysis = AnalysisUseCases(
        lambda: InMemoryAnalysisUnitOfWork(Store.empty(), FactStore.empty(), {}, {}),
        FakeClock(),
        SequentialIds(),
        prompts,
    )
    server = MCPServer("test")
    register_gap_tools(server, analysis, prompts)
    return server


async def answer_gap(agent: MCPServer) -> Any:
    tools = {t.name: t for t in await agent.list_tools()}
    assert "answer_gap" in tools
    return tools["answer_gap"]


async def test_the_server_offers_exactly_answer_gap(agent: MCPServer) -> None:
    assert [t.name for t in await agent.list_tools()] == ["answer_gap"]


async def test_the_input_schema_has_the_job_gap_number_answer_and_facts(
    agent: MCPServer,
) -> None:
    schema = (await answer_gap(agent)).input_schema
    properties = schema["properties"]

    assert {name: properties[name]["type"] for name in list(properties)[:3]} == {
        "job_id": "integer",
        "gap_number": "integer",
        "has_experience": "boolean",
    }
    assert schema["required"] == ["job_id", "gap_number", "has_experience"]
    assert properties["facts"]["type"] == "array"
    fact = schema["$defs"]["FactIn"]
    assert sorted(fact["properties"]) == ["kind", "text"]
    assert fact["properties"]["kind"]["enum"] == [
        "experience",
        "achievement",
        "project",
        "skill",
        "education",
        "language",
    ]


async def test_the_output_schema_lists_the_closed_gap_and_its_facts(
    agent: MCPServer,
) -> None:
    output = (await answer_gap(agent)).output_schema
    assert output is not None
    assert sorted(output["properties"]) == [
        "closed",
        "fact_ids",
        "facts",
        "gap",
        "gap_number",
        "has_experience",
        "job_id",
    ]


async def test_the_description_comes_from_the_prompt_catalog_and_is_neutral(
    agent: MCPServer,
) -> None:
    description = (await answer_gap(agent)).description or ""

    assert description == FilePrompts.load(CATALOG).get(PromptKey.MCP_TOOL_ANSWER_GAP)
    assert not re.search(r"\b(Taras|he|his|him|himself)\b", description)


async def test_the_description_states_the_rules_of_the_answer(agent: MCPServer) -> None:
    description = (await answer_gap(agent)).description or ""

    assert "has_experience" in description
    assert "approved" in description  # факти — лише зі схваленим формулюванням
    assert "never ask again" in description  # «ні» теж зберігається
    assert "gap_number" in description


async def test_it_is_a_write_tool(agent: MCPServer) -> None:
    assert (await answer_gap(agent)).annotations == WRITE
