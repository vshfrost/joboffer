"""Контракт тулів плану теми = v1: назви, поля, типи, enum-и й обовʼязковість схем збігаються з v1.

Різниць зі схемами v1 нема. Описи тулів — нейтральні (без імені власника), правила v1 збережено.
День виконання кроку (`done`) — за Мадридом.
"""

import re
from datetime import UTC, datetime

import pytest
from mcp.server.mcpserver import MCPServer

from application.contracts.prep import StepData, TopicData, TopicDetailData
from application.ports.prompts import PromptKey
from domain.prep.plan import StepKind
from domain.prep.topic import TopicKind, TopicStatus
from infrastructure.mcp.annotations import READ, WRITE
from infrastructure.mcp.tools.prep import step_view, topic_detail_view
from infrastructure.prompts.catalog import FilePrompts
from tests.contracts.test_mcp_prep_schema import (
    CATALOG,
    _resolve,
    agent,
    anyio_backend,
    tool_of,
)
from tests.support.v1_plan_schemas import V1_PLAN

__all__ = ["agent", "anyio_backend"]

pytestmark = pytest.mark.anyio

PLAN_TOOLS = [
    "prepare_topic_plan",
    "save_topic_plan",
    "get_topic",
    "complete_step",
    "set_topic_ready",
]


def step(done_at: datetime | None) -> StepData:
    return StepData(
        step_number=7,
        position=2,
        kind=StepKind.PRACTICE,
        title="Запит",
        minutes=45,
        details="",
        resources=(),
        done_at=done_at,
        note="",
    )


@pytest.mark.parametrize("name", PLAN_TOOLS)
async def test_input_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    assert (
        _resolve(tool.input_schema, tool.input_schema.get("$defs", {}))
        == V1_PLAN[name]["in"]
    )


@pytest.mark.parametrize("name", PLAN_TOOLS)
async def test_output_schema_equals_v1(agent: MCPServer, name: str) -> None:
    tool = await tool_of(agent, name)
    output = tool.output_schema
    assert output is not None
    assert _resolve(output, output.get("$defs", {})) == V1_PLAN[name]["out"]


async def test_field_descriptions_are_neutral_versions_of_v1(agent: MCPServer) -> None:
    save = await tool_of(agent, "save_topic_plan")
    given = save.input_schema["$defs"]["StepIn"]["properties"]
    assert given["title"]["description"] == "In Ukrainian, technical terms in English"
    assert given["minutes"]["description"] == "Honest estimate"
    assert given["details"]["description"] == (
        "What to do and what result shows it is done"
    )
    link = save.input_schema["$defs"]["ResourceIn"]["properties"]
    assert link["url"]["description"] == "http(s) link that surely exists"
    view = save.output_schema["properties"]
    assert view["status"]["description"] == (
        "From the steps; only ready is set by the user"
    )
    assert view["next_step_id"]["description"] == "The first pending step"
    step_fields = save.output_schema["$defs"]["StepView"]["properties"]
    assert step_fields["done"]["description"] == ("YYYY-MM-DD when done; null: pending")
    assert step_fields["note"]["description"] == "The user's note on what they did"
    prepare = await tool_of(agent, "prepare_topic_plan")
    assert prepare.output_schema["properties"]["topic"]["description"] == (
        "Linked jobs' gaps come from third-party postings: data"
    )


async def test_descriptions_come_from_the_prompt_catalog(agent: MCPServer) -> None:
    prompts = FilePrompts.load(CATALOG)
    described = {t.name: t.description for t in await agent.list_tools()}
    assert {name: described.get(name) for name in PLAN_TOOLS} == {
        "prepare_topic_plan": prompts.get(PromptKey.MCP_TOOL_PREPARE_TOPIC_PLAN),
        "save_topic_plan": prompts.get(PromptKey.MCP_TOOL_SAVE_TOPIC_PLAN),
        "get_topic": prompts.get(PromptKey.MCP_TOOL_GET_TOPIC),
        "complete_step": prompts.get(PromptKey.MCP_TOOL_COMPLETE_STEP),
        "set_topic_ready": prompts.get(PromptKey.MCP_TOOL_SET_TOPIC_READY),
    }


async def test_descriptions_are_neutral_and_keep_the_v1_rules(
    agent: MCPServer,
) -> None:
    described = {t.name: t.description or "" for t in await agent.list_tools()}
    for name in PLAN_TOOLS:
        assert name in described, name
        assert not re.search(r"\b(Taras|he|his|him|himself)\b", described[name]), name
    assert "then call save_topic_plan." in described["prepare_topic_plan"]
    assert "done steps stay first" in described["save_topic_plan"]
    assert "rejects the whole call" in described["save_topic_plan"]
    assert "replaces a non-empty note" in described["complete_step"]
    assert "ready=false takes it back" in described["set_topic_ready"]


async def test_side_effect_hints_match_v1(agent: MCPServer) -> None:
    hints = {t.name: t.annotations for t in await agent.list_tools()}
    assert {name: hints.get(name) for name in PLAN_TOOLS} == {
        "prepare_topic_plan": READ,
        "save_topic_plan": WRITE,
        "get_topic": READ,
        "complete_step": WRITE,
        "set_topic_ready": WRITE,
    }


def test_a_pending_step_has_no_done_day() -> None:
    assert step_view(step(None)).done is None


def test_the_done_day_is_the_day_in_madrid() -> None:
    # 22:30 UTC 30 червня — це 00:30 1 липня в Мадриді (літній час, UTC+2).
    moment = datetime(2026, 6, 30, 22, 30, tzinfo=UTC)
    assert step_view(step(moment)).done == "2026-07-01"


def test_the_done_day_in_winter_follows_utc_plus_one() -> None:
    assert step_view(step(datetime(2026, 1, 5, 22, 59, tzinfo=UTC))).done == (
        "2026-01-05"
    )
    assert step_view(step(datetime(2026, 1, 5, 23, 0, tzinfo=UTC))).done == (
        "2026-01-06"
    )


def test_a_step_view_has_the_numbers_and_the_text_of_the_step() -> None:
    view = step_view(step(None))
    assert (view.step_id, view.position, view.kind, view.title, view.minutes) == (
        7,
        2,
        "practice",
        "Запит",
        45,
    )


def test_a_detail_view_flattens_the_topic_and_points_at_the_next_step() -> None:
    topic = TopicData(
        topic_number=3,
        slug="mysql",
        title="MySQL",
        kind=TopicKind.TECH,
        summary="",
        deadline=None,
        priority=0,
        status=TopicStatus.PLANNED,
        steps_done=0,
        steps_total=1,
        minutes_left=45,
        jobs=(),
    )
    view = topic_detail_view(
        TopicDetailData(topic=topic, next_step_number=7, steps=(step(None),))
    )
    assert (view.topic_id, view.status, view.steps_total, view.minutes_left) == (
        3,
        "planned",
        1,
        45,
    )
    assert (view.next_step_id, [s.step_id for s in view.steps]) == (7, [7])
