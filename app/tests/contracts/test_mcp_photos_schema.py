"""Контракт тула `list_photos` = v1: поля, типи й обовʼязковість схем збігаються з v1.

Різниць зі схемами v1 нема. Будь-яка розбіжність — помилка тесту.
"""

import re
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.photos.use_cases import PhotoUseCases
from application.ports.prompts import PromptKey
from infrastructure.mcp.annotations import READ
from infrastructure.mcp.tools.photos import register_photo_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.photos import FakeProcessor, InMemoryPhotoUnitOfWork, Store
from tests.support.v1_photo_schemas import V1

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"


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
    store = Store()
    photos = PhotoUseCases(
        lambda: InMemoryPhotoUnitOfWork(store),
        FakeProcessor(),
        FakeClock(),
        SequentialIds(),
    )
    server = MCPServer("test")
    register_photo_tools(
        server,
        photos,
        FilePrompts.load(CATALOG),
        lambda number: f"https://web.example/api/photos/{number}.jpg",
        "https://web.example/profile/photos",
    )
    return server


async def tool_of(agent: MCPServer) -> Any:
    return next(t for t in await agent.list_tools() if t.name == "list_photos")


async def test_the_server_offers_exactly_list_photos(agent: MCPServer) -> None:
    assert [t.name for t in await agent.list_tools()] == ["list_photos"]


async def test_input_schema_equals_v1(agent: MCPServer) -> None:
    tool = await tool_of(agent)
    assert (
        _resolve(tool.input_schema, tool.input_schema.get("$defs", {}))
        == V1["list_photos"]["in"]
    )


async def test_output_schema_equals_v1(agent: MCPServer) -> None:
    output = (await tool_of(agent)).output_schema
    assert output is not None
    assert _resolve(output, output.get("$defs", {})) == V1["list_photos"]["out"]


async def test_field_descriptions_say_the_v1_things_without_naming_a_person(
    agent: MCPServer,
) -> None:
    output = (await tool_of(agent)).output_schema
    view = output["$defs"]["PhotoView"]["properties"]
    assert view["added"]["description"] == "YYYY-MM-DD"
    assert view["last_used"]["description"] == (
        "YYYY-MM-DD of the last CV with it; null: never"
    )
    assert output["properties"]["photos"]["description"] == "Newest first"
    assert output["properties"]["suggested_photo_id"]["description"] == (
        "Suggest this one: the last used in a CV, else the newest; null: no photos"
    )
    for description in (
        view["preview_url"]["description"],
        output["properties"]["photo_upload_url"]["description"],
    ):
        assert not re.search(r"\bTaras\b", description)


async def test_the_description_comes_from_the_prompt_catalog_and_is_neutral(
    agent: MCPServer,
) -> None:
    description = (await tool_of(agent)).description
    assert description == FilePrompts.load(CATALOG).get(PromptKey.MCP_TOOL_LIST_PHOTOS)
    assert not re.search(r"\b(Taras|he|his|him|himself)\b", description or "")
    assert "photo_upload_url" in (description or "")


async def test_the_side_effect_hints_match_v1(agent: MCPServer) -> None:
    assert (await tool_of(agent)).annotations == READ
