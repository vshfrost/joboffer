"""Контракт фактових тулів = v1: поля, типи, enum-и й обовʼязковість схем збігаються з v1.

Усі сім тулів повні. Єдині заплановані розширення v1 — джерело факту: необов'язковий `source`
у `save_facts` і поля `source`, `job_id` у фактах, які повертають `save_facts`, `list_facts`,
`update_fact`, `confirm_facts`. Будь-яка інша розбіжність — помилка тесту.
"""

import copy
import re
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.facts.use_cases import FactUseCases
from application.ports.prompts import PromptKey
from infrastructure.mcp.annotations import DELETE, READ, WRITE
from infrastructure.mcp.tools.facts import register_fact_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.support.clock import FakeClock
from tests.support.facts import InMemoryFactUnitOfWork, Store
from tests.support.ids import SequentialIds
from tests.support.v1_fact_schemas import V1

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
TOOLS = [
    "save_original_cv",
    "get_original_cv",
    "save_facts",
    "list_facts",
    "update_fact",
    "confirm_facts",
    "delete_fact",
]


SOURCE = {"enum": ["cv", "chat", "manual"], "type": "string"}
JOB_ID = {"anyOf": [{"type": "integer"}, {"type": "null"}]}


def _detailed(fact: dict[str, Any]) -> None:
    fact["properties"] |= {"source": SOURCE, "job_id": JOB_ID}
    fact["required"] = [*fact["required"], "source", "job_id"]


def expected(name: str, direction: str) -> dict[str, Any]:
    """Схема v1 плюс заплановані розширення про джерело факту."""
    schema: dict[str, Any] = copy.deepcopy(V1[name][direction])
    if direction == "in" and name == "save_facts":
        schema["properties"]["source"] = SOURCE
    if direction == "out" and name in {"save_facts", "list_facts", "confirm_facts"}:
        key = "added" if name == "save_facts" else "facts"
        _detailed(schema["properties"][key]["items"])
    if direction == "out" and name == "update_fact":
        _detailed(schema)
    return schema


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
    facts = FactUseCases(
        lambda: InMemoryFactUnitOfWork(store), FakeClock(), SequentialIds()
    )
    server = MCPServer("test")
    register_fact_tools(server, facts, FilePrompts.load(CATALOG))
    return server


async def tool_of(agent: MCPServer, name: str) -> Any:
    return next(t for t in await agent.list_tools() if t.name == name)


async def test_the_server_offers_exactly_the_seven_fact_tools(agent: MCPServer) -> None:
    assert sorted(t.name for t in await agent.list_tools()) == sorted(TOOLS)


@pytest.mark.parametrize("name", TOOLS)
async def test_input_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    assert _resolve(tool.input_schema, tool.input_schema.get("$defs", {})) == expected(
        name, "in"
    )


@pytest.mark.parametrize("name", TOOLS)
async def test_output_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    output = tool.output_schema
    assert output is not None
    assert _resolve(output, output.get("$defs", {})) == expected(name, "out")


async def test_field_descriptions_are_the_v1_text(agent: MCPServer) -> None:
    saved = await tool_of(agent, "get_original_cv")
    assert saved.output_schema["properties"]["saved"]["description"] == "YYYY-MM-DD"
    skipped = await tool_of(agent, "save_facts")
    assert skipped.output_schema["properties"]["skipped_duplicates"]["description"] == (
        "Texts that were already saved and were skipped"
    )
    fact_in = skipped.input_schema["$defs"]["FactIn"]["properties"]
    assert fact_in["text"]["description"] == (
        "One atomic claim, max 500 chars; numbers and names exactly as in the CV"
    )


async def test_descriptions_come_from_the_prompt_catalog(agent: MCPServer) -> None:
    prompts = FilePrompts.load(CATALOG)
    described = {t.name: t.description for t in await agent.list_tools()}
    assert described == {
        "save_original_cv": prompts.get(PromptKey.MCP_TOOL_SAVE_ORIGINAL_CV),
        "get_original_cv": prompts.get(PromptKey.MCP_TOOL_GET_ORIGINAL_CV),
        "save_facts": prompts.get(PromptKey.MCP_TOOL_SAVE_FACTS),
        "list_facts": prompts.get(PromptKey.MCP_TOOL_LIST_FACTS),
        "update_fact": prompts.get(PromptKey.MCP_TOOL_UPDATE_FACT),
        "confirm_facts": prompts.get(PromptKey.MCP_TOOL_CONFIRM_FACTS),
        "delete_fact": prompts.get(PromptKey.MCP_TOOL_DELETE_FACT),
    }


async def test_descriptions_are_neutral_and_keep_the_v1_rules(agent: MCPServer) -> None:
    described = {t.name: t.description or "" for t in await agent.list_tools()}
    for name, text in described.items():
        assert not re.search(r"\b(Taras|he|his|him|himself)\b", text), name
    assert "only the facts the user explicitly approved" in described["confirm_facts"]
    assert "Any unknown id rejects the whole call." in described["confirm_facts"]
    assert "unconfirmed until the user approves it again" in described["update_fact"]
    assert "One invalid fact rejects the whole call." in described["save_facts"]
    assert described["delete_fact"] == "Delete a fact for good."


async def test_side_effect_hints_match_v1(agent: MCPServer) -> None:
    hints = {t.name: t.annotations for t in await agent.list_tools()}
    assert hints == {
        "save_original_cv": WRITE,
        "get_original_cv": READ,
        "save_facts": WRITE,
        "list_facts": READ,
        "update_fact": WRITE,
        "confirm_facts": WRITE,
        "delete_fact": DELETE,
    }
