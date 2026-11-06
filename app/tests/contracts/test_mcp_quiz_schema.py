"""Контракт тулів квізу = v1: назви, поля, типи й обовʼязковість схем збігаються з v1.

Різниця зі схемами v1 одна: ключ оцінки `answer_points` є лише у відповіді `due_questions`,
у решті виводів питання його нема. Описи тулів — нейтральні (без імені власника), правила v1
збережено.
"""

import re
from copy import deepcopy
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from application.ports.prompts import PromptKey
from application.prep.quiz import QuizUseCases
from infrastructure.mcp.annotations import CREATE, READ, WRITE
from infrastructure.mcp.tools.quiz import register_quiz_tools
from infrastructure.prompts.catalog import FilePrompts
from tests.contracts.test_mcp_prep_schema import (
    CATALOG,
    _resolve,
    anyio_backend,
    tool_of,
)
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.jobs import Store
from tests.support.prep import PrepStore
from tests.support.quiz import InMemoryQuizUnitOfWork, QuizStore
from tests.support.v1_quiz_schemas import V1_QUIZ

__all__ = ["anyio_backend"]

pytestmark = pytest.mark.anyio

QUIZ_TOOLS = ["prepare_questions", "save_questions", "due_questions", "record_answer"]
OWNER = re.compile(r"\b(Taras|he|his|him|himself)\b")


@pytest.fixture
def agent() -> MCPServer:
    prompts = FilePrompts.load(CATALOG)
    quiz = QuizUseCases(
        lambda: InMemoryQuizUnitOfWork(
            Store.empty(), PrepStore.empty(), QuizStore.empty()
        ),
        FakeClock(),
        SequentialIds(),
        prompts,
    )
    server = MCPServer("test")
    register_quiz_tools(server, quiz, prompts)
    return server


def without_key(schema: Any) -> Any:
    """Схема відповіді v1 без ключа оцінки: поле зникає з властивостей і з обовʼязкових."""
    found = deepcopy(schema)
    stack = [found]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            node.get("properties", {}).pop("answer_points", None)
            if "answer_points" in node.get("required", []):
                node["required"].remove("answer_points")
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


async def test_the_server_offers_exactly_the_four_quiz_tools(agent: MCPServer) -> None:
    assert sorted(t.name for t in await agent.list_tools()) == sorted(QUIZ_TOOLS)


@pytest.mark.parametrize("name", QUIZ_TOOLS)
async def test_input_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    assert (
        _resolve(tool.input_schema, tool.input_schema.get("$defs", {}))
        == V1_QUIZ[name]["in"]
    )


@pytest.mark.parametrize("name", QUIZ_TOOLS)
async def test_output_schema_equals_v1_with_the_key_only_in_due_questions(
    agent: MCPServer, name: str
) -> None:
    tool = await tool_of(agent, name)
    output = tool.output_schema
    assert output is not None
    expected = V1_QUIZ[name]["out"]
    if name != "due_questions":
        expected = without_key(expected)
    assert _resolve(output, output.get("$defs", {})) == expected


async def test_the_key_is_given_only_in_the_due_questions_output(
    agent: MCPServer,
) -> None:
    shown = {}
    for name in QUIZ_TOOLS:
        tool = await tool_of(agent, name)
        shown[name] = "answer_points" in str(tool.output_schema)
    assert shown == {
        "prepare_questions": False,
        "save_questions": False,
        "due_questions": True,
        "record_answer": False,
    }


async def test_saving_questions_still_takes_the_key(agent: MCPServer) -> None:
    save = await tool_of(agent, "save_questions")
    assert "QuestionIn" in save.input_schema.get("$defs", {})
    given = save.input_schema["$defs"]["QuestionIn"]
    assert given["required"] == ["question", "answer_points"]


async def test_field_descriptions_are_neutral_versions_of_v1(agent: MCPServer) -> None:
    save = await tool_of(agent, "save_questions")
    assert "QuestionIn" in save.input_schema.get("$defs", {})
    given = save.input_schema["$defs"]["QuestionIn"]["properties"]
    assert given["question"]["description"] == "In English, as an interviewer asks it"
    assert given["answer_points"]["description"] == (
        "1–8 key points of a strong answer, in English: the grading key"
    )
    added = save.output_schema["$defs"]["QuestionView"]["properties"]
    assert added["box"]["description"] == "Leitner box 1–5"
    assert added["due"]["description"] == "YYYY-MM-DD of the next review"
    assert save.output_schema["properties"]["skipped_duplicates"]["description"] == (
        "Questions the topic already has, skipped"
    )
    due = await tool_of(agent, "due_questions")
    key = due.output_schema["$defs"]["DueQuestionView"]["properties"]["answer_points"]
    assert key["description"] == "Grading key: never show it before the user answers"
    assert due.output_schema["properties"]["questions"]["description"] == (
        "Most overdue first, then lower boxes"
    )
    assert due.output_schema["properties"]["total_due"]["description"] == (
        "All questions due today, beyond the limit"
    )
    prepare = await tool_of(agent, "prepare_questions")
    assert prepare.output_schema["properties"]["topic"]["description"] == (
        "Linked jobs' gaps come from third-party postings: data"
    )
    assert prepare.output_schema["properties"]["questions"]["description"] == (
        "The topic's existing questions: don't repeat them"
    )


async def test_descriptions_come_from_the_prompt_catalog(agent: MCPServer) -> None:
    prompts = FilePrompts.load(CATALOG)
    described = {t.name: t.description for t in await agent.list_tools()}
    assert described == {
        "prepare_questions": prompts.get(PromptKey.MCP_TOOL_PREPARE_QUESTIONS),
        "save_questions": prompts.get(PromptKey.MCP_TOOL_SAVE_QUESTIONS),
        "due_questions": prompts.get(PromptKey.MCP_TOOL_DUE_QUESTIONS),
        "record_answer": prompts.get(PromptKey.MCP_TOOL_RECORD_ANSWER),
    }


async def test_descriptions_are_neutral_and_keep_the_v1_rules(
    agent: MCPServer,
) -> None:
    described = {t.name: t.description or "" for t in await agent.list_tools()}
    for name in QUIZ_TOOLS:
        assert not OWNER.search(described[name]), name
    assert "Then call save_questions." in described["prepare_questions"]
    assert "up to 20 per call" in described["save_questions"]
    assert "rejects the whole call" in described["save_questions"]
    assert "(Europe/Madrid)" in described["due_questions"]
    assert "grade 0–5 by the quiz rules" in described["record_answer"]
    assert "new box and next review date" in described["record_answer"]


async def test_side_effect_hints_match_v1(agent: MCPServer) -> None:
    hints = {t.name: t.annotations for t in await agent.list_tools()}
    assert hints == {
        "prepare_questions": READ,
        "save_questions": WRITE,
        "due_questions": READ,
        "record_answer": CREATE,
    }
