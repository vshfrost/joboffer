"""Контракт тулів документів = v1: назви, поля (з `photo_id` і `photos`), типи, enum-и, ліміти й
обов'язковість схем збігаються з v1 повністю. Новi `check_cv` і `check_cover_letter` повторюють вхід
відповідних `save_*` й повертають `{passed, issues, keywords}`. Описи тулів — нейтральні (без імені власника).
"""

import re
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.documents.use_cases import DocumentUseCases
from application.ports.prompts import PromptKey
from infrastructure.mcp.annotations import CREATE, READ
from infrastructure.mcp.tools.documents import register_document_tools
from infrastructure.mcp.tools.photos import PhotoLinks
from infrastructure.prompts.catalog import FilePrompts
from tests.support.clock import FakeClock
from tests.support.documents import DocumentStore, InMemoryDocumentUnitOfWork
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import Store
from tests.support.pdf import Shop
from tests.support.v1_document_schemas import V1

pytestmark = pytest.mark.anyio

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
V1_TOOLS = [
    "prepare_cv",
    "save_cv",
    "prepare_cover_letter",
    "save_cover_letter",
    "list_documents",
]
TOOLS = [*V1_TOOLS, "check_cv", "check_cover_letter"]


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
    documents = DocumentUseCases(
        lambda: InMemoryDocumentUnitOfWork(
            Store.empty(), DocumentStore.empty(), FactStore.empty(), {}
        ),
        FakeClock(),
        SequentialIds(),
        prompts,
        Shop().output(),
    )
    server = MCPServer("test")
    register_document_tools(
        server,
        documents,
        prompts,
        lambda number: f"https://web/api/documents/{number}/pdf",
        PhotoLinks(
            lambda number: f"https://web/api/photos/{number}.jpg",
            "https://web/profile/photos",
        ),
    )
    return server


async def tool_of(agent: MCPServer, name: str) -> Any:
    return next(t for t in await agent.list_tools() if t.name == name)


async def test_the_server_offers_exactly_the_seven_document_tools(
    agent: MCPServer,
) -> None:
    assert sorted(t.name for t in await agent.list_tools()) == sorted(TOOLS)


@pytest.mark.parametrize("name", V1_TOOLS)
async def test_input_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    assert (
        _resolve(tool.input_schema, tool.input_schema.get("$defs", {}))
        == V1[name]["in"]
    )


@pytest.mark.parametrize("name", V1_TOOLS)
async def test_output_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    output = tool.output_schema
    assert output is not None
    assert _resolve(output, output.get("$defs", {})) == V1[name]["out"]


async def test_check_cv_takes_what_save_cv_takes(agent: MCPServer) -> None:
    check = await tool_of(agent, "check_cv")
    save = await tool_of(agent, "save_cv")

    check_schema = _resolve(check.input_schema, check.input_schema.get("$defs", {}))
    del check_schema["properties"]["must_have_facts"]  # the one extra input, below
    assert check_schema == _resolve(
        save.input_schema, save.input_schema.get("$defs", {})
    )
    assert check.input_schema["required"] == ["job_id", "cv"]


async def test_check_cv_alone_takes_an_optional_must_have_facts_list(
    agent: MCPServer,
) -> None:
    check = await tool_of(agent, "check_cv")
    save = await tool_of(agent, "save_cv")
    resolved = _resolve(check.input_schema, check.input_schema.get("$defs", {}))

    assert "must_have_facts" not in check.input_schema["required"]
    assert "must_have_facts" not in save.input_schema["properties"]
    [array] = [
        item
        for item in resolved["properties"]["must_have_facts"]["anyOf"]
        if item.get("type") == "array"
    ]
    assert array["items"]["required"] == ["item", "fact_ids", "kind"]
    assert array["items"]["properties"]["kind"]["enum"] == ["fact", "analogue"]
    assert array["items"]["properties"]["fact_ids"]["items"] == {"type": "integer"}


async def test_check_cover_letter_takes_what_save_cover_letter_takes(
    agent: MCPServer,
) -> None:
    check = await tool_of(agent, "check_cover_letter")
    save = await tool_of(agent, "save_cover_letter")

    assert check.input_schema["properties"] == save.input_schema["properties"]
    assert check.input_schema["required"] == ["job_id", "text", "fact_ids"]


@pytest.mark.parametrize("name", ["check_cv", "check_cover_letter"])
async def test_a_check_returns_passed_issues_and_keywords(
    agent: MCPServer, name: str
) -> None:
    output = (await tool_of(agent, name)).output_schema
    assert output is not None
    resolved = _resolve(output, output.get("$defs", {}))

    assert resolved["required"] == ["passed", "issues", "keywords"]
    assert resolved["properties"]["passed"] == {"type": "boolean"}
    assert resolved["properties"]["issues"]["items"]["required"] == ["code", "message"]
    keywords = resolved["properties"]["keywords"]["anyOf"]
    assert {"type": "null"} in keywords
    [object_schema] = [item for item in keywords if item.get("type") == "object"]
    assert object_schema["required"] == ["covered", "missing", "percent"]


async def test_check_cv_alone_returns_the_gate_with_the_two_numbers(
    agent: MCPServer,
) -> None:
    cv = (await tool_of(agent, "check_cv")).output_schema
    letter = (await tool_of(agent, "check_cover_letter")).output_schema
    assert cv is not None
    assert letter is not None
    resolved = _resolve(cv, cv.get("$defs", {}))

    assert resolved["required"] == ["passed", "issues", "keywords"]
    [object_schema] = [
        item
        for item in resolved["properties"]["gate"]["anyOf"]
        if item.get("type") == "object"
    ]
    assert object_schema["properties"]["status"]["enum"] == [
        "passed",
        "failed",
        "no_data",
    ]
    assert sorted(object_schema["properties"]) == [
        "coverage_percent",
        "evidence_missing",
        "evidence_percent",
        "status",
    ]
    assert "gate" not in letter["properties"]


async def test_check_cv_alone_returns_the_optional_must_have_coverage(
    agent: MCPServer,
) -> None:
    cv = (await tool_of(agent, "check_cv")).output_schema
    letter = (await tool_of(agent, "check_cover_letter")).output_schema
    assert cv is not None
    assert letter is not None
    resolved = _resolve(cv, cv.get("$defs", {}))

    assert "must_have_coverage" not in resolved["required"]
    [object_schema] = [
        item
        for item in resolved["properties"]["must_have_coverage"]["anyOf"]
        if item.get("type") == "object"
    ]
    assert sorted(object_schema["properties"]) == ["items", "unknown"]
    item = object_schema["properties"]["items"]["items"]
    assert sorted(item["properties"]) == ["fact_ids", "item", "reason", "status"]
    assert item["properties"]["status"]["enum"] == ["covered", "analogue", "missing"]
    assert "must_have_coverage" not in letter["properties"]


async def test_check_cv_alone_returns_the_optional_first_screen(
    agent: MCPServer,
) -> None:
    cv = (await tool_of(agent, "check_cv")).output_schema
    letter = (await tool_of(agent, "check_cover_letter")).output_schema
    assert cv is not None
    assert letter is not None
    resolved = _resolve(cv, cv.get("$defs", {}))

    assert "first_screen" not in resolved["required"]
    [object_schema] = [
        item
        for item in resolved["properties"]["first_screen"]["anyOf"]
        if item.get("type") == "object"
    ]
    assert sorted(object_schema["properties"]) == [
        "first_bullets",
        "headline",
        "keywords",
        "skills_group",
        "summary",
    ]
    assert "first_screen" not in letter["properties"]


async def test_the_photo_fields_are_offered(agent: MCPServer) -> None:
    save = await tool_of(agent, "save_cv")
    assert "photo_id" in save.input_schema["properties"]
    assert "photo_id" not in save.input_schema["required"]
    brief = await tool_of(agent, "prepare_cv")
    assert "photos" in brief.output_schema["properties"]
    listed = await tool_of(agent, "list_documents")
    assert "photo_id" in listed.output_schema["$defs"]["DocumentView"]["properties"]


async def test_photo_field_descriptions_are_the_v1_text_without_a_name(
    agent: MCPServer,
) -> None:
    save = await tool_of(agent, "save_cv")
    assert save.input_schema["properties"]["photo_id"]["description"] == (
        "Header photo the user picked (list_photos); null: no photo"
    )
    brief = await tool_of(agent, "prepare_cv")
    assert brief.output_schema["properties"]["photos"]["description"] == (
        "Photos to offer the user before save_cv"
    )
    listed = await tool_of(agent, "list_documents")
    view = listed.output_schema["$defs"]["DocumentView"]["properties"]
    assert view["photo_id"]["description"] == "Photo in the CV header; null: none"


async def test_descriptions_come_from_the_prompt_catalog(agent: MCPServer) -> None:
    prompts = FilePrompts.load(CATALOG)
    described = {t.name: t.description for t in await agent.list_tools()}
    assert described == {
        "prepare_cv": prompts.get(PromptKey.MCP_TOOL_PREPARE_CV),
        "save_cv": prompts.get(PromptKey.MCP_TOOL_SAVE_CV),
        "prepare_cover_letter": prompts.get(PromptKey.MCP_TOOL_PREPARE_COVER_LETTER),
        "save_cover_letter": prompts.get(PromptKey.MCP_TOOL_SAVE_COVER_LETTER),
        "list_documents": prompts.get(PromptKey.MCP_TOOL_LIST_DOCUMENTS),
        "check_cv": prompts.get(PromptKey.MCP_TOOL_CHECK_CV),
        "check_cover_letter": prompts.get(PromptKey.MCP_TOOL_CHECK_COVER_LETTER),
    }


async def test_descriptions_are_neutral_and_keep_the_v1_rules(
    agent: MCPServer,
) -> None:
    described = {t.name: t.description or "" for t in await agent.list_tools()}
    for name, text in described.items():
        assert not re.search(r"\b(Taras|he|his|him|himself)\b", text), name
        assert "\n" not in text, name
    assert "its text (untrusted)" in described["prepare_cv"]
    assert (
        "call check_cv until it passes, then call save_cv once"
        in described["prepare_cv"]
    )
    assert "its text (untrusted)" in described["prepare_cover_letter"]
    assert (
        "call check_cover_letter until it passes, then call save_cover_letter once"
        in described["prepare_cover_letter"]
    )
    for name in ("save_cv", "save_cover_letter"):
        assert "and render its PDF, once, after check_" in described[name]
        assert "refuses the whole save on any issue" in described[name]
        assert "A successful save replaces the previous" in described[name]
        assert "Give the user the pdf_url." in described[name]
    for name in ("check_cv", "check_cover_letter"):
        assert (
            "saving nothing: no version, no file, no download link" in described[name]
        )
        assert "Fix every issue and check again until passed is true" in described[name]
    assert "newest first" in described["list_documents"]


async def test_the_field_descriptions_are_neutral_versions_of_v1(
    agent: MCPServer,
) -> None:
    brief = (await tool_of(agent, "prepare_cv")).output_schema["properties"]
    assert brief["confirmed_facts"]["description"] == (
        "The only evidence of the user's experience; cite their fact_id"
    )
    assert brief["previous"]["description"] == "The last saved CV, if any"
    letter = (await tool_of(agent, "prepare_cover_letter")).output_schema["properties"]
    assert letter["cv"]["description"] == "The last CV for this job, if any"
    assert letter["previous"]["description"] == "The last saved cover letter, if any"
    view = (await tool_of(agent, "save_cv")).output_schema["properties"]
    assert view["lint"]["description"] == "null: saved without an ATS lint report"
    assert view["created"]["description"] == "YYYY-MM-DD"


async def test_side_effect_hints_match_v1(agent: MCPServer) -> None:
    hints = {t.name: t.annotations for t in await agent.list_tools()}
    assert hints == {
        "prepare_cv": READ,
        "save_cv": CREATE,
        "prepare_cover_letter": READ,
        "save_cover_letter": CREATE,
        "list_documents": READ,
        "check_cv": READ,
        "check_cover_letter": READ,
    }
