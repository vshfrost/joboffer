"""Контракт тулів джерел = v1: поля, типи й обовʼязковість схем збігаються з v1; тул читання лише читає,
тул запиту створює запис у черзі; описи — з каталогу промптів і без імені користувача."""

import re
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.ports.prompts import PromptKey
from application.sources.overview import SourceOverviewUseCases
from infrastructure.mcp.annotations import CREATE, READ
from infrastructure.mcp.tools.sources import register_source_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.contracts.test_mcp_applications_schema import _resolve
from tests.support.clock import FakeClock
from tests.support.source_overview import InMemorySourceOverviewUnitOfWork
from tests.support.source_runs import SourceRunStore
from tests.support.v1_source_schemas import V1

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
TOOLS = ["get_sources", "refresh_sources"]
NAME = re.compile(r"\b(Taras|he|his|him|himself)\b")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def agent() -> MCPServer:
    store = SourceRunStore()
    overview = SourceOverviewUseCases(
        lambda: InMemorySourceOverviewUnitOfWork(store), FakeClock()
    )
    server = MCPServer("test")
    register_source_tools(server, overview, FilePrompts.load(CATALOG), "http://web")
    return server


async def tool_of(agent: MCPServer, name: str) -> Any:
    found = [t for t in await agent.list_tools() if t.name == name]
    assert found, f"тула {name} нема"
    return found[0]


async def test_the_server_offers_exactly_the_two_source_tools(agent: MCPServer) -> None:
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


async def test_listing_only_reads_and_requesting_creates_a_queue_row(
    agent: MCPServer,
) -> None:
    assert (await tool_of(agent, "get_sources")).annotations == READ
    assert (await tool_of(agent, "refresh_sources")).annotations == CREATE


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("get_sources", PromptKey.MCP_TOOL_GET_SOURCES),
        ("refresh_sources", PromptKey.MCP_TOOL_REFRESH_SOURCES),
    ],
)
async def test_the_description_comes_from_the_catalog_and_names_no_person(
    agent: MCPServer, name: str, key: PromptKey
) -> None:
    description = (await tool_of(agent, name)).description

    assert description == FilePrompts.load(CATALOG).get(key)
    assert not NAME.search(description or "")


async def test_the_descriptions_keep_the_v1_meaning(agent: MCPServer) -> None:
    assert (await tool_of(agent, "get_sources")).description == (
        "The sources the user's new jobs come from — company career pages (Greenhouse, "
        "Ashby, Lever) and RSS feeds (DOU, Djinni) — each with its last run (when, found / "
        "imported / skipped by their profile filters / duplicate / error). The server "
        "refreshes them on a schedule; jobs from them arrive with full text. Also "
        "filtered_out: saved jobs their current profile filters would no longer take "
        "(count and job_ids; hide them with dismiss_jobs only after they say yes). They "
        "edit the lists themselves at settings_url."
    )
    assert (await tool_of(agent, "refresh_sources")).description == (
        "Ask the server to refresh all sources now. This only queues the request (nothing "
        "is fetched here): the server picks it up within about a minute — then call "
        "get_sources to see the result and list_jobs for new jobs. At most 2 requests per "
        "30 minutes."
    )


async def test_field_descriptions_name_no_person(agent: MCPServer) -> None:
    schema = (await tool_of(agent, "get_sources")).output_schema

    assert not NAME.search(str(schema))
