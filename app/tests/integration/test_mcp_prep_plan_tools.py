"""Тули плану теми через SDK-клієнт: DCR → токен → `tools/list` і виклики на справжньому Postgres."""

from datetime import UTC, datetime
from typing import Any

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from domain.shared.local_time import local_day
from tests.integration.test_agent_http import PUBLIC, Agent
from tests.integration.test_mcp_job_tools import data, error_text
from tests.integration.test_mcp_prep_tools import MYSQL, STAR, analysed, save
from tests.integration.test_mcp_profile_tools import (
    TOOLS,
    agent,
    anyio_backend,
    call,
    katya,
    taras,
)

__all__ = ["agent", "anyio_backend"]

pytestmark = pytest.mark.anyio

NAMES = (
    "prepare_topic_plan",
    "save_topic_plan",
    "get_topic",
    "complete_step",
    "set_topic_ready",
)
LEARN: dict[str, Any] = {
    "kind": "learn",
    "title": "Прочитати про індекси",
    "minutes": 60,
}
PRACTICE: dict[str, Any] = {
    "kind": "practice",
    "title": "Написати запити з JOIN",
    "minutes": 120,
    "details": "Результат: запити в репозиторії.",
    "resources": [{"title": "Документація MySQL", "url": "https://dev.mysql.com/doc/"}],
}
CHECK: dict[str, Any] = {"kind": "check", "title": "Розповісти вголос", "minutes": 30}
PLAN = [LEARN, PRACTICE, CHECK]


async def topic_with_job(
    agent: Agent, token: str, *, who: str = "taras@example.com"
) -> int:
    job = await analysed(agent, token, 82, who=who)
    saved = await save(agent, token, job, MYSQL)
    return int(saved["topics"][0]["topic_id"])


async def plan(
    agent: Agent, token: str, topic: int, steps: list[dict[str, Any]]
) -> dict[str, Any]:
    return data(
        await call(agent, token, "save_topic_plan", {"topic_id": topic, "steps": steps})
    )


async def complete(
    agent: Agent, token: str, step: int, note: str | None = None
) -> dict[str, Any]:
    arguments: dict[str, Any] = {"step_id": step}
    if note is not None:
        arguments["note"] = note
    return data(await call(agent, token, "complete_step", arguments))


async def test_tools_list_has_the_five_plan_tools_with_the_catalog_descriptions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    for name in NAMES:
        assert name in tools
        assert tools[name].description == (TOOLS / f"{name}.md").read_text(
            encoding="utf-8"
        )


async def test_the_plan_brief_has_the_topic_its_jobs_and_the_rules(
    agent: Agent,
) -> None:
    token = await taras(agent)
    topic = await topic_with_job(agent, token)

    brief = data(await call(agent, token, "prepare_topic_plan", {"topic_id": topic}))

    assert brief["topic"]["slug"] == "mysql-query-optimization"
    assert brief["topic"]["status"] == "new"
    assert brief["topic"]["steps"] == []
    assert brief["topic"]["next_step_id"] is None
    assert [(j["score"], j["gap"]) for j in brief["topic"]["jobs"]] == [
        (82, "Немає досвіду з MySQL")
    ]
    assert brief["rules"].startswith(
        "Write a study plan for this topic so that the user can discuss it"
    )
    assert "Taras" not in brief["rules"]


async def test_save_returns_the_topic_with_its_steps_progress_and_the_next_step(
    agent: Agent,
) -> None:
    token = await taras(agent)
    topic = await topic_with_job(agent, token)

    saved = await plan(agent, token, topic, PLAN)

    assert (saved["topic_id"], saved["status"]) == (topic, "planned")
    assert (saved["steps_done"], saved["steps_total"], saved["minutes_left"]) == (
        0,
        3,
        210,
    )
    assert saved["next_step_id"] == 1
    assert saved["steps"] == [
        {
            "step_id": 1,
            "position": 1,
            "kind": "learn",
            "title": "Прочитати про індекси",
            "minutes": 60,
            "details": "",
            "resources": [],
            "done": None,
            "note": "",
        },
        {
            "step_id": 2,
            "position": 2,
            "kind": "practice",
            "title": "Написати запити з JOIN",
            "minutes": 120,
            "details": "Результат: запити в репозиторії.",
            "resources": [
                {"title": "Документація MySQL", "url": "https://dev.mysql.com/doc/"}
            ],
            "done": None,
            "note": "",
        },
        {
            "step_id": 3,
            "position": 3,
            "kind": "check",
            "title": "Розповісти вголос",
            "minutes": 30,
            "details": "",
            "resources": [],
            "done": None,
            "note": "",
        },
    ]
    assert data(await call(agent, token, "get_topic", {"topic_id": topic})) == saved


async def test_an_invalid_plan_is_a_tool_error_with_the_step_number_and_changes_nothing(
    agent: Agent,
) -> None:
    token = await taras(agent)
    topic = await topic_with_job(agent, token)
    await plan(agent, token, topic, PLAN)

    bad = await call(
        agent,
        token,
        "save_topic_plan",
        {"topic_id": topic, "steps": [LEARN, {**PRACTICE, "minutes": 0}, CHECK]},
    )
    short = await call(
        agent, token, "save_topic_plan", {"topic_id": topic, "steps": [PRACTICE, CHECK]}
    )

    assert "Крок 2: minutes — від 1 до 480." in error_text(bad)
    assert (
        "У плані 2 кроків (разом із виконаними 0) — треба від 3 до 12."
        in error_text(short)
    )
    kept = data(await call(agent, token, "get_topic", {"topic_id": topic}))
    assert [s["step_id"] for s in kept["steps"]] == [1, 2, 3]


async def test_a_step_kind_outside_the_schema_is_rejected(agent: Agent) -> None:
    token = await taras(agent)
    topic = await topic_with_job(agent, token)
    result = await call(
        agent,
        token,
        "save_topic_plan",
        {"topic_id": topic, "steps": [{**LEARN, "kind": "read"}, PRACTICE, CHECK]},
    )
    assert "practice" in error_text(result)


async def test_complete_step_marks_it_done_with_the_madrid_day_and_the_note(
    agent: Agent,
) -> None:
    token = await taras(agent)
    topic = await topic_with_job(agent, token)
    await plan(agent, token, topic, PLAN)

    before = local_day(datetime.now(UTC))
    done = await complete(agent, token, 1, "Прочитав розділ про B-tree")
    after = local_day(datetime.now(UTC))

    first = done["steps"][0]
    assert first["done"] in {before, after}
    assert first["note"] == "Прочитав розділ про B-tree"
    assert (done["status"], done["steps_done"], done["minutes_left"]) == (
        "learning",
        1,
        150,
    )
    assert done["next_step_id"] == 2


async def test_completing_again_keeps_the_date_and_replaces_a_non_empty_note(
    agent: Agent,
) -> None:
    token = await taras(agent)
    topic = await topic_with_job(agent, token)
    await plan(agent, token, topic, PLAN)
    first = (await complete(agent, token, 1, "Перша"))["steps"][0]

    again = (await complete(agent, token, 1, "Друга"))["steps"][0]
    kept = (await complete(agent, token, 1))["steps"][0]

    assert (again["done"], again["note"]) == (first["done"], "Друга")
    assert (kept["done"], kept["note"]) == (first["done"], "Друга")


async def test_a_missing_foreign_step_and_a_too_long_note_are_tool_errors(
    agent: Agent,
) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    topic = await topic_with_job(agent, taras_token)
    await plan(agent, taras_token, topic, PLAN)

    missing = await call(agent, taras_token, "complete_step", {"step_id": 99})
    foreign = await call(agent, katya_token, "complete_step", {"step_id": 1})
    long_note = await call(
        agent, taras_token, "complete_step", {"step_id": 1, "note": "н" * 2001}
    )

    assert "Крок 99 не знайдено." in error_text(missing)
    assert "Крок 1 не знайдено." in error_text(foreign)
    assert "Нотатка — до 2000 символів." in error_text(long_note)
    topic_view = data(await call(agent, taras_token, "get_topic", {"topic_id": topic}))
    assert topic_view["steps_done"] == 0


async def test_replacing_the_plan_keeps_the_done_steps_first(agent: Agent) -> None:
    token = await taras(agent)
    topic = await topic_with_job(agent, token)
    await plan(agent, token, topic, PLAN)
    await complete(agent, token, 1, "Готово")

    saved = await plan(agent, token, topic, [PRACTICE, CHECK])

    assert [(s["step_id"], s["done"] is not None) for s in saved["steps"]] == [
        (1, True),
        (4, False),
        (5, False),
    ]
    assert saved["steps_done"] == 1
    assert saved["next_step_id"] == 4


async def test_set_topic_ready_marks_it_and_ready_false_returns_the_status_from_the_steps(
    agent: Agent,
) -> None:
    token = await taras(agent)
    topic = await topic_with_job(agent, token)
    await plan(agent, token, topic, PLAN)
    await complete(agent, token, 2)

    ready = data(await call(agent, token, "set_topic_ready", {"topic_id": topic}))
    taken_back = data(
        await call(agent, token, "set_topic_ready", {"topic_id": topic, "ready": False})
    )

    assert ready["status"] == "ready"
    assert taken_back["status"] == "practicing"
    assert taken_back["steps_done"] == 1


async def test_a_missing_or_foreign_topic_is_a_tool_error_for_every_plan_tool(
    agent: Agent,
) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    await topic_with_job(agent, taras_token)

    for name, arguments in (
        ("prepare_topic_plan", {"topic_id": 1}),
        ("save_topic_plan", {"topic_id": 1, "steps": PLAN}),
        ("get_topic", {"topic_id": 1}),
        ("set_topic_ready", {"topic_id": 1}),
    ):
        result = await call(agent, katya_token, name, arguments)
        assert "Тему 1 не знайдено." in error_text(result), name
    mine = data(await call(agent, taras_token, "get_topic", {"topic_id": 1}))
    assert (mine["status"], mine["steps_total"]) == ("new", 0)


async def test_the_topic_lists_show_the_real_status_and_counters(agent: Agent) -> None:
    token = await taras(agent)
    job = await analysed(agent, token, 82)
    await save(agent, token, job, MYSQL, STAR)
    await plan(agent, token, 1, PLAN)
    await complete(agent, token, 2)

    listed = data(await call(agent, token, "list_prep_topics"))["topics"]

    by_slug = {t["slug"]: t for t in listed}
    mysql = by_slug["mysql-query-optimization"]
    assert (
        mysql["status"],
        mysql["steps_done"],
        mysql["steps_total"],
        mysql["minutes_left"],
    ) == ("practicing", 1, 3, 90)
    star = by_slug["star-conflict"]
    assert (star["status"], star["steps_total"], star["minutes_left"]) == ("new", 0, 0)
    brief = data(await call(agent, token, "prepare_prep_topics", {"job_id": job}))
    assert {t["slug"]: t["status"] for t in brief["topics"]} == {
        "mysql-query-optimization": "practicing",
        "star-conflict": "new",
    }
