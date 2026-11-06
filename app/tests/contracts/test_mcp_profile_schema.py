"""Контракт тулів профілю = v1 (`agent/views.py::Profile`): поля, типи, enum-и, обовʼязковість, описи."""

from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.ports.prompts import PromptKey
from application.profile.use_cases import ProfileUseCases
from infrastructure.mcp.annotations import READ, WRITE
from infrastructure.mcp.tools.profile import register_profile_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.support.clock import FakeClock
from tests.support.profile import InMemoryProfileUnitOfWork

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
MODES = {"type": "string", "enum": ["remote", "hybrid", "onsite"]}
LEVELS = {
    "type": "string",
    "enum": ["junior", "middle", "senior", "lead", "principal"],
}
STRINGS = {"type": "array", "items": {"type": "string"}}
TEXT = {"type": "string"}

V1_LOCATION = {
    "type": "object",
    "properties": {
        "place": TEXT,
        "aliases": STRINGS,
        "work_modes": {"type": "array", "items": MODES, "minItems": 1},
    },
    "required": ["place", "work_modes"],
}
V1_PROFILE = {
    "type": "object",
    "properties": {
        "roles": STRINGS,
        "work_modes": {"type": "array", "items": MODES},
        "locations": {"type": "array", "items": V1_LOCATION},
        "include_unknown_mode": {"type": "boolean"},
        "relocation": {"type": "boolean"},
        "target_domains": STRINGS,
        "seniority": {"type": "array", "items": LEVELS},
        "min_salary_eur": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "stop_words": STRINGS,
        "title_keywords": STRINGS,
        "title_exclude": STRINGS,
        "full_name": TEXT,
        "email": TEXT,
        "phone": TEXT,
        "linkedin_url": TEXT,
        "city": TEXT,
        "github_url": TEXT,
        "work_authorization": TEXT,
    },
}
V1_DESCRIPTIONS = {
    "locations": "Where job sources are searched (empty: anywhere)",
    "include_unknown_mode": "A source posting with no stated work mode: true — a matching place is enough, false — skip it",
    "target_domains": "Industries the job search targets, e.g. fintech, payments: examples for the domain-fit part of the analysis rubric",
    "min_salary_eur": "Gross per year, EUR",
    "title_keywords": "Job sources import a posting only if its title contains one of these words (empty: any title)",
    "title_exclude": "Job sources skip a posting whose title contains one of these words",
    "full_name": "CV header",
    "email": "CV header",
    "phone": "CV header, international format",
    "linkedin_url": "CV header, https://…",
    "city": "CV header, e.g. Valencia, Spain",
    "github_url": "CV header, https://…",
    "work_authorization": "CV header, e.g. Spain / EU work authorization",
}
V1_LOCATION_DESCRIPTIONS = {
    "place": "City, country or region, e.g. Valencia",
    "aliases": "Other spellings and languages of the place, e.g. Валенсія; a synonym also matches as the start of a word",
    "work_modes": "Work modes accepted at this place",
}


def _resolve(node: Any, defs: dict[str, Any]) -> Any:
    """Розгортає `$ref` і прибирає title / description / default: порівнюється форма, а не оздоблення."""
    if isinstance(node, list):
        return [_resolve(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        return _resolve(defs[node["$ref"].rsplit("/", 1)[1]], defs)
    return {
        key: _resolve(value, defs)
        for key, value in node.items()
        if key not in {"title", "description", "default", "$defs"}
    }


def _properties(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    return {name: _resolve(schema, defs) for name, schema in node["properties"].items()}


@pytest.fixture
def agent() -> MCPServer:
    store: dict[Any, Any] = {}
    saved_at: dict[Any, Any] = {}
    profiles = ProfileUseCases(
        lambda: InMemoryProfileUnitOfWork(store, saved_at), FakeClock()
    )
    server = MCPServer("test")
    register_profile_tools(server, profiles, FilePrompts.load(CATALOG))
    return server


async def test_the_server_offers_exactly_the_two_profile_tools(
    agent: MCPServer,
) -> None:
    names = sorted(tool.name for tool in await agent.list_tools())
    assert names == ["get_profile", "update_profile"]


async def test_update_profile_takes_one_required_profile_argument(
    agent: MCPServer,
) -> None:
    tool = next(t for t in await agent.list_tools() if t.name == "update_profile")
    schema = tool.input_schema
    assert list(schema["properties"]) == ["profile"]
    assert schema["required"] == ["profile"]


async def test_profile_fields_types_enums_and_requiredness_equal_v1(
    agent: MCPServer,
) -> None:
    tool = next(t for t in await agent.list_tools() if t.name == "update_profile")
    schema = tool.input_schema
    defs = schema["$defs"]
    profile = defs[schema["properties"]["profile"]["$ref"].rsplit("/", 1)[1]]
    assert _properties(profile, defs) == V1_PROFILE["properties"]
    assert profile.get("required", []) == []
    location_ref = profile["properties"]["locations"]["items"]["$ref"]
    location = defs[location_ref.rsplit("/", 1)[1]]
    assert _properties(location, defs) == V1_LOCATION["properties"]
    assert location["required"] == V1_LOCATION["required"]


async def test_get_profile_returns_the_same_profile_shape(agent: MCPServer) -> None:
    tool = next(t for t in await agent.list_tools() if t.name == "get_profile")
    assert tool.input_schema.get("properties", {}) == {}
    output = tool.output_schema
    assert output is not None
    assert _properties(output, output.get("$defs", {})) == V1_PROFILE["properties"]


async def test_field_descriptions_are_the_v1_text(agent: MCPServer) -> None:
    tool = next(t for t in await agent.list_tools() if t.name == "update_profile")
    defs = tool.input_schema["$defs"]
    profile = defs["Profile"]["properties"]
    for name, description in V1_DESCRIPTIONS.items():
        assert profile[name]["description"] == description
    location = defs["SearchLocationView"]["properties"]
    for name, description in V1_LOCATION_DESCRIPTIONS.items():
        assert location[name]["description"] == description


async def test_descriptions_come_from_the_prompt_catalog(agent: MCPServer) -> None:
    prompts = FilePrompts.load(CATALOG)
    described = {tool.name: tool.description for tool in await agent.list_tools()}
    assert described == {
        "get_profile": prompts.get(PromptKey.MCP_TOOL_GET_PROFILE),
        "update_profile": prompts.get(PromptKey.MCP_TOOL_UPDATE_PROFILE),
    }


async def test_side_effect_hints_are_read_for_get_and_idempotent_write_for_update(
    agent: MCPServer,
) -> None:
    hints = {tool.name: tool.annotations for tool in await agent.list_tools()}
    assert hints == {"get_profile": READ, "update_profile": WRITE}
