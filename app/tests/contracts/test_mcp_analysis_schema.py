"""Контракт тулів аналізу = v1: назви, поля, типи, enum-и, ліміти й обовʼязковість схем збігаються з v1.

Різниць зі схемами v1 нема. Описи тулів — нейтральні (без імені власника), правила v1 збережено.
"""

import re
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.analysis.use_cases import AnalysisUseCases
from application.ports.prompts import PromptKey
from infrastructure.mcp.annotations import READ, WRITE
from infrastructure.mcp.tools.analysis import register_analysis_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.support.analysis import InMemoryAnalysisUnitOfWork
from tests.support.clock import FakeClock
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import Store
from tests.support.v1_analysis_schemas import V1

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
TOOLS = ["prepare_analysis", "save_analysis"]


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
    prompts = FilePrompts.load(CATALOG)
    analysis = AnalysisUseCases(
        lambda: InMemoryAnalysisUnitOfWork(Store.empty(), FactStore.empty(), {}, {}),
        FakeClock(),
        SequentialIds(),
        prompts,
    )
    server = MCPServer("test")
    register_analysis_tools(server, analysis, prompts)
    return server


async def tool_of(agent: MCPServer, name: str) -> Any:
    return next(t for t in await agent.list_tools() if t.name == name)


async def test_the_server_offers_exactly_the_two_analysis_tools(
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


async def test_field_descriptions_are_neutral_versions_of_v1(agent: MCPServer) -> None:
    prepare = await tool_of(agent, "prepare_analysis")
    brief = prepare.output_schema["properties"]
    assert brief["confirmed_facts"]["description"] == (
        "The only evidence of the user's experience"
    )
    assert brief["previous"]["description"] == "The last saved analysis, if any"
    save = await tool_of(agent, "save_analysis")
    view = save.output_schema["properties"]
    assert (
        view["filters_passed"]["description"] == "false: fails the user's hard filters"
    )
    assert view["flags"]["description"] == "Which hard filters failed, in Ukrainian"
    assert view["updated"]["description"] == "YYYY-MM-DD"
    given = save.input_schema["$defs"]["AnalysisIn"]["properties"]
    assert given["salary_min_eur"]["description"] == "Gross per year, EUR"
    assert given["relocation"]["description"] == "Company offers relocation support"


async def test_descriptions_come_from_the_prompt_catalog(agent: MCPServer) -> None:
    prompts = FilePrompts.load(CATALOG)
    described = {t.name: t.description for t in await agent.list_tools()}
    assert described == {
        "prepare_analysis": prompts.get(PromptKey.MCP_TOOL_PREPARE_ANALYSIS),
        "save_analysis": prompts.get(PromptKey.MCP_TOOL_SAVE_ANALYSIS),
    }


async def test_descriptions_are_neutral_and_keep_the_v1_rules(
    agent: MCPServer,
) -> None:
    described = {t.name: t.description or "" for t in await agent.list_tools()}
    for name, text in described.items():
        assert not re.search(r"\b(Taras|he|his|him|himself)\b", text), name
    assert "its text (untrusted)" in described["prepare_analysis"]
    assert "Then call save_analysis." in described["prepare_analysis"]
    assert "replaces the previous one" in described["save_analysis"]
    assert "returns the flags" in described["save_analysis"]


async def test_side_effect_hints_match_v1(agent: MCPServer) -> None:
    hints = {t.name: t.annotations for t in await agent.list_tools()}
    assert hints == {"prepare_analysis": READ, "save_analysis": WRITE}
