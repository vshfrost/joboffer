"""Контракт тула `get_document_download`: назва, вхід, поля відповіді й опис.

Тула нема у v1: контракт — вимоги K-K. Агент з shell (curl) за `url` качає PDF без сесії веба
і прикріплює локальний файл до форми розширенням браузера.
"""

from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.documents.downloads import DocumentDownloads
from application.ports.prompts import PromptKey
from infrastructure.mcp.annotations import CREATE
from infrastructure.mcp.tools.document_downloads import (
    register_document_download_tool,
)
from infrastructure.prompts.catalog import FilePrompts
from tests.support.downloads import Library

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def build(downloads: DocumentDownloads) -> MCPServer:
    server = MCPServer("test")
    register_document_download_tool(
        server,
        downloads,
        FilePrompts.load(CATALOG),
        lambda token: f"https://web/api/documents/download/{token}",
    )
    return server


@pytest.fixture
def agent() -> MCPServer:
    return build(Library().downloads)


async def tool_of(agent: MCPServer) -> Any:
    (tool,) = await agent.list_tools()
    return tool


async def test_the_server_offers_exactly_get_document_download(
    agent: MCPServer,
) -> None:
    assert (await tool_of(agent)).name == "get_document_download"


async def test_the_input_is_one_required_integer_document_id(agent: MCPServer) -> None:
    schema = (await tool_of(agent)).input_schema

    assert schema["properties"]["document_id"]["type"] == "integer"
    assert list(schema["properties"]) == ["document_id"]
    assert schema["required"] == ["document_id"]


async def test_the_output_has_url_file_name_and_expires_at(agent: MCPServer) -> None:
    schema = (await tool_of(agent)).output_schema

    assert schema is not None
    assert {name: field["type"] for name, field in schema["properties"].items()} == {
        "url": "string",
        "file_name": "string",
        "expires_at": "string",
    }
    assert schema["properties"]["expires_at"]["format"] == "date-time"
    assert sorted(schema["required"]) == ["expires_at", "file_name", "url"]


async def test_the_description_comes_from_the_prompt_catalog(agent: MCPServer) -> None:
    prompts = FilePrompts.load(CATALOG)

    assert (await tool_of(agent)).description == prompts.get(
        PromptKey.MCP_TOOL_GET_DOCUMENT_DOWNLOAD
    )


async def test_the_description_tells_what_the_link_is_for_and_how_long_it_lives(
    agent: MCPServer,
) -> None:
    text = (await tool_of(agent)).description or ""

    assert "\n" not in text
    assert "download" in text
    assert "single-use" in text
    assert "10 minutes" in text
    assert "no session" in text
    assert "local file" in text
    assert "document_id" in text


async def test_the_tool_creates_a_new_link_on_every_call(agent: MCPServer) -> None:
    assert (await tool_of(agent)).annotations == CREATE


async def test_the_description_puts_the_browser_fetch_before_the_shell_fallback(
    agent: MCPServer,
) -> None:
    text = (await tool_of(agent)).description or ""

    assert "fetch" in text
    assert "real browser" in text
    assert "Downloads folder" in text
    assert text.index("fetch") < text.index("curl")
    assert "call this tool again for a new link on every retry" in text
