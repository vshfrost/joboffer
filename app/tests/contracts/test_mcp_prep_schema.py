"""Контракт тулів тем підготовки = v1: назви, поля, типи, enum-и й обовʼязковість схем збігаються з v1.

Різниця зі схемами v1 одна: ATS-5 додав у бриф тем `cv_lines`. Описи тулів — нейтральні (без імені власника), правила v1 збережено.
"""

import copy
import re
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.ports.prompts import PromptKey
from application.prep.use_cases import PrepUseCases
from infrastructure.mcp.annotations import READ, WRITE
from infrastructure.mcp.tools.prep import register_prep_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.jobs import Store
from tests.support.prep import InMemoryPrepUnitOfWork, PrepStore
from tests.support.v1_prep_schemas import V1

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
TOOLS = ["prepare_prep_topics", "save_prep_topics", "list_prep_topics"]


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
    prep = PrepUseCases(
        lambda: InMemoryPrepUnitOfWork(Store.empty(), PrepStore.empty()),
        FakeClock(),
        SequentialIds(),
        prompts,
    )
    server = MCPServer("test")
    register_prep_tools(server, prep, prompts)
    return server


async def tool_of(agent: MCPServer, name: str) -> Any:
    tools = {tool.name: tool for tool in await agent.list_tools()}
    assert name in tools, f"тулу {name} нема"
    return tools[name]


async def test_the_server_offers_exactly_the_eight_prep_tools(agent: MCPServer) -> None:
    # K50 додав п'ять тулів плану теми до трьох тулів тем із K49.
    plan = [
        "prepare_topic_plan",
        "save_topic_plan",
        "get_topic",
        "complete_step",
        "set_topic_ready",
    ]
    assert sorted(t.name for t in await agent.list_tools()) == sorted(TOOLS + plan)


@pytest.mark.parametrize("name", TOOLS)
async def test_input_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    assert (
        _resolve(tool.input_schema, tool.input_schema.get("$defs", {}))
        == V1[name]["in"]
    )


_CV_LINE = {
    "properties": {
        "text": {"type": "string"},
        "facts": {
            "items": {
                "properties": {
                    "fact_id": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["fact_id", "text"],
                "type": "object",
            },
            "type": "array",
        },
    },
    "required": ["text", "facts"],
    "type": "object",
}


def _expected_out(name: str) -> dict[str, Any]:
    """v1, крім ATS-5: бриф тем має ще й рядки CV вакансії з їхніми фактами."""
    expected: dict[str, Any] = copy.deepcopy(V1[name]["out"])
    if name == "prepare_prep_topics":
        expected["properties"]["cv_lines"] = {"items": _CV_LINE, "type": "array"}
        expected["required"].append("cv_lines")
    return expected


@pytest.mark.parametrize("name", TOOLS)
async def test_output_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    output = tool.output_schema
    assert output is not None
    assert _resolve(output, output.get("$defs", {})) == _expected_out(name)


async def test_field_descriptions_are_neutral_versions_of_v1(agent: MCPServer) -> None:
    prepare = await tool_of(agent, "prepare_prep_topics")
    brief = prepare.output_schema["properties"]
    assert brief["topics"]["description"] == (
        "All of the user's topics by priority: reuse a slug instead of a duplicate"
    )
    save = await tool_of(agent, "save_prep_topics")
    given = save.input_schema["$defs"]["TopicIn"]["properties"]
    assert given["slug"]["description"] == "Lowercase latin words joined by hyphens"
    assert given["title"]["description"] == "In Ukrainian, technical terms in English"
    assert given["gap"]["description"] == (
        "The gap or requirement of this job the topic closes"
    )
    assert given["summary"]["description"] == "What to prepare, in Ukrainian"
    assert given["deadline"]["description"] == "YYYY-MM-DD or empty"
    view = save.output_schema["$defs"]["TopicView"]["properties"]
    assert view["deadline"]["description"] == "YYYY-MM-DD"
    assert view["priority"]["description"] == "Sum of the linked jobs' scores"
    assert view["status"]["description"] == (
        "From the steps; only ready is set by the user"
    )
    assert view["minutes_left"]["description"] == "Estimate of the pending steps"


async def test_descriptions_come_from_the_prompt_catalog(agent: MCPServer) -> None:
    prompts = FilePrompts.load(CATALOG)
    described = {
        t.name: t.description for t in await agent.list_tools() if t.name in TOOLS
    }
    assert described == {
        "prepare_prep_topics": prompts.get(PromptKey.MCP_TOOL_PREPARE_PREP_TOPICS),
        "save_prep_topics": prompts.get(PromptKey.MCP_TOOL_SAVE_PREP_TOPICS),
        "list_prep_topics": prompts.get(PromptKey.MCP_TOOL_LIST_PREP_TOPICS),
    }


async def test_descriptions_are_neutral_and_keep_the_v1_rules(
    agent: MCPServer,
) -> None:
    described = {
        t.name: t.description or "" for t in await agent.list_tools() if t.name in TOOLS
    }
    assert sorted(described) == sorted(TOOLS)
    for name, text in described.items():
        assert not re.search(r"\b(Taras|he|his|him|himself)\b", text), name
    assert "then call save_prep_topics." in described["prepare_prep_topics"]
    assert "instead of creating a duplicate" in described["save_prep_topics"]
    assert "rejects the whole call" in described["save_prep_topics"]
    assert "closer deadline first among equals" in described["list_prep_topics"]


async def test_side_effect_hints_match_v1(agent: MCPServer) -> None:
    hints = {t.name: t.annotations for t in await agent.list_tools() if t.name in TOOLS}
    assert hints == {
        "prepare_prep_topics": READ,
        "save_prep_topics": WRITE,
        "list_prep_topics": READ,
    }
