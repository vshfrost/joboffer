"""Контракт тулів пакета до інтерв'ю = v1: назви, поля, типи, enum-и й обовʼязковість схем
збігаються з v1. Різниць зі схемами v1 нема. Описи тулів і полів — нейтральні (без імені
власника), правила v1 збережено.
"""

import re

import pytest
from mcp.server.mcpserver import MCPServer

from application.ports.prompts import PromptKey
from application.prep.kit import InterviewKitUseCases
from infrastructure.mcp.annotations import CREATE, READ
from infrastructure.mcp.tools.interview import register_interview_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.contracts.test_mcp_prep_schema import (
    CATALOG,
    _resolve,
    anyio_backend,
    tool_of,
)
from tests.support.clock import FakeClock
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import Store
from tests.support.kit import InMemoryKitUnitOfWork, KitStore
from tests.support.prep import PrepStore
from tests.support.v1_kit_schemas import V1_KIT

__all__ = ["anyio_backend"]

pytestmark = pytest.mark.anyio

KIT_TOOLS = ["prepare_interview_kit", "save_interview_kit"]
OWNER = re.compile(r"\b(Taras|he|his|him|himself)\b")


@pytest.fixture
def agent() -> MCPServer:
    prompts = FilePrompts.load(CATALOG)
    kits = InterviewKitUseCases(
        lambda: InMemoryKitUnitOfWork(
            Store.empty(), PrepStore.empty(), FactStore.empty(), KitStore.empty()
        ),
        FakeClock(),
        SequentialIds(),
        prompts,
    )
    server = MCPServer("test")
    register_interview_tools(server, kits, prompts)
    return server


async def test_the_server_offers_exactly_the_two_interview_kit_tools(
    agent: MCPServer,
) -> None:
    assert sorted(t.name for t in await agent.list_tools()) == sorted(KIT_TOOLS)


@pytest.mark.parametrize("name", KIT_TOOLS)
async def test_input_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    assert (
        _resolve(tool.input_schema, tool.input_schema.get("$defs", {}))
        == V1_KIT[name]["in"]
    )


@pytest.mark.parametrize("name", KIT_TOOLS)
async def test_output_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    output = tool.output_schema
    assert output is not None
    assert _resolve(output, output.get("$defs", {})) == V1_KIT[name]["out"]


async def test_field_descriptions_of_the_saved_kit_are_the_v1_text(
    agent: MCPServer,
) -> None:
    save = await tool_of(agent, "save_interview_kit")
    defs = save.input_schema["$defs"]
    question = defs["KitQuestionIn"]["properties"]
    assert (
        question["question"]["description"] == "In English, as the interviewer asks it"
    )
    assert question["topic_id"]["description"] == (
        "The prep topic that prepares the answer; null: none"
    )
    story = defs["StarStoryIn"]["properties"]
    assert story["title"]["description"] == "Short name of the story"
    assert story["fact_ids"]["description"] == (
        "Confirmed facts the story rests on, 1–10"
    )
    kit = save.output_schema["properties"]
    assert kit["created"]["description"] == "YYYY-MM-DD"


async def test_field_descriptions_of_the_brief_are_neutral_versions_of_v1(
    agent: MCPServer,
) -> None:
    brief = (await tool_of(agent, "prepare_interview_kit")).output_schema["properties"]
    assert brief["analysis"]["description"] == (
        "Must-haves and gaps; null: not analysed yet"
    )
    assert brief["topics"]["description"] == (
        "The user's prep topics for this job, by priority: use their topic_id"
    )
    assert brief["confirmed_facts"]["description"] == (
        "The only evidence of the user's experience; cite their fact_id"
    )
    assert brief["previous"]["description"] == "The last saved kit, if any"


async def test_descriptions_come_from_the_prompt_catalog(agent: MCPServer) -> None:
    prompts = FilePrompts.load(CATALOG)
    described = {t.name: t.description for t in await agent.list_tools()}
    assert described == {
        "prepare_interview_kit": prompts.get(PromptKey.MCP_TOOL_PREPARE_INTERVIEW_KIT),
        "save_interview_kit": prompts.get(PromptKey.MCP_TOOL_SAVE_INTERVIEW_KIT),
    }


async def test_descriptions_are_neutral_and_keep_the_v1_rules(
    agent: MCPServer,
) -> None:
    described = {t.name: t.description or "" for t in await agent.list_tools()}
    for name in KIT_TOOLS:
        assert not OWNER.search(described[name]), name
    assert "its text (untrusted)" in described["prepare_interview_kit"]
    assert "Then call save_interview_kit." in described["prepare_interview_kit"]
    assert "5–20 likely questions" in described["save_interview_kit"]
    assert (
        "3–6 STAR stories each citing confirmed facts"
        in described["save_interview_kit"]
    )
    assert "3–8 questions for the company" in described["save_interview_kit"]
    assert "fix the listed problem and call again" in described["save_interview_kit"]


async def test_side_effect_hints_match_v1(agent: MCPServer) -> None:
    hints = {t.name: t.annotations for t in await agent.list_tools()}
    assert hints == {"prepare_interview_kit": READ, "save_interview_kit": CREATE}
