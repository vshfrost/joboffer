"""Тули тем підготовки через SDK-клієнт: DCR → токен → `tools/list` і виклики на справжньому Postgres."""

from itertools import count
from typing import Any

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from tests.integration.test_agent_http import PUBLIC, Agent
from tests.integration.test_mcp_analysis_tools import save as save_analysis
from tests.integration.test_mcp_analysis_tools import seed
from tests.integration.test_mcp_job_tools import data, error_text
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

_bodies = count(1)
NAMES = ("prepare_prep_topics", "save_prep_topics", "list_prep_topics")
MYSQL: dict[str, Any] = {
    "slug": "mysql-query-optimization",
    "title": "Оптимізація запитів MySQL",
    "kind": "tech",
    "gap": "Немає досвіду з MySQL",
    "summary": "Індекси й EXPLAIN.",
    "deadline": "2026-03-15",
}
STAR: dict[str, Any] = {
    "slug": "star-conflict",
    "title": "Конфлікт у команді",
    "kind": "behavioral",
    "gap": "Потрібні історії про конфлікти",
}


def only(items: list[dict[str, Any]]) -> dict[str, Any]:
    assert len(items) == 1, items
    return items[0]


async def analysed(
    agent: Agent, token: str, score: int = 82, *, who: str = "taras@example.com"
) -> int:
    number = await seed(agent, f"Python role {next(_bodies)}.", who=who)
    await save_analysis(agent, token, number, score=score, gaps=["MySQL", "STAR"])
    return number


async def save(
    agent: Agent, token: str, job_id: int, *topics: dict[str, Any]
) -> dict[str, Any]:
    result = await call(
        agent, token, "save_prep_topics", {"job_id": job_id, "topics": list(topics)}
    )
    return data(result)


async def test_tools_list_has_the_three_prep_tools_with_the_catalog_descriptions(
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


async def test_the_brief_has_the_job_its_gaps_the_topics_and_the_rules(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)

    brief = data(await call(agent, token, "prepare_prep_topics", {"job_id": number}))

    assert brief["job"] == {
        "job_id": number,
        "title": "Backend",
        "company": "Acme",
        "score": 82,
        "summary": "S.",
        "must_have": [],
        "nice_to_have": [],
        "gaps": ["MySQL", "STAR"],
    }
    assert brief["topics"] == []
    assert brief["rules"].startswith(
        "Propose interview-prep topics that close this job's gaps."
    )


async def test_a_missing_job_and_a_job_without_analysis_are_tool_errors(
    agent: Agent,
) -> None:
    token = await taras(agent)
    missing = await call(agent, token, "prepare_prep_topics", {"job_id": 7})
    assert "Вакансію 7 не знайдено." in error_text(missing)
    raw = await seed(agent)
    refused = await call(agent, token, "prepare_prep_topics", {"job_id": raw})
    not_analysed = (
        f"Вакансію {raw} ще не проаналізовано: спершу prepare_analysis → save_analysis."
    )
    assert not_analysed in error_text(refused)
    saving = await call(
        agent, token, "save_prep_topics", {"job_id": raw, "topics": [MYSQL]}
    )
    assert not_analysed in error_text(saving)


async def test_save_returns_the_topics_in_request_order_with_the_v1_fields(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)

    saved = await save(agent, token, number, STAR, MYSQL)

    assert saved == {
        "topics": [
            {
                "topic_id": 1,
                "slug": "star-conflict",
                "title": "Конфлікт у команді",
                "kind": "behavioral",
                "summary": "",
                "deadline": None,
                "priority": 82,
                "status": "new",
                "steps_done": 0,
                "steps_total": 0,
                "minutes_left": 0,
                "jobs": [
                    {
                        "job_id": number,
                        "title": "Backend",
                        "company": "Acme",
                        "score": 82,
                        "gap": "Потрібні історії про конфлікти",
                    }
                ],
            },
            {
                "topic_id": 2,
                "slug": "mysql-query-optimization",
                "title": "Оптимізація запитів MySQL",
                "kind": "tech",
                "summary": "Індекси й EXPLAIN.",
                "deadline": "2026-03-15",
                "priority": 82,
                "status": "new",
                "steps_done": 0,
                "steps_total": 0,
                "minutes_left": 0,
                "jobs": [
                    {
                        "job_id": number,
                        "title": "Backend",
                        "company": "Acme",
                        "score": 82,
                        "gap": "Немає досвіду з MySQL",
                    }
                ],
            },
        ]
    }


async def test_an_existing_slug_is_updated_and_linked_to_the_second_job(
    agent: Agent,
) -> None:
    token = await taras(agent)
    first = await analysed(agent, token, 82)
    second = await analysed(agent, token, 60)
    await save(agent, token, first, MYSQL)

    saved = await save(
        agent,
        token,
        second,
        {**MYSQL, "title": "MySQL глибше", "gap": "Потрібен EXPLAIN", "deadline": ""},
    )

    topic = only(saved["topics"])
    assert (topic["topic_id"], topic["title"], topic["deadline"]) == (
        1,
        "MySQL глибше",
        None,
    )
    assert topic["priority"] == 142
    assert [(job["job_id"], job["gap"]) for job in topic["jobs"]] == [
        (first, "Немає досвіду з MySQL"),
        (second, "Потрібен EXPLAIN"),
    ]


async def test_list_shows_the_topics_by_priority(agent: Agent) -> None:
    token = await taras(agent)
    weak = await analysed(agent, token, 40)
    strong = await analysed(agent, token, 90)
    await save(agent, token, weak, STAR)
    await save(agent, token, strong, MYSQL)

    listed = data(await call(agent, token, "list_prep_topics"))

    assert [topic["slug"] for topic in listed["topics"]] == [
        "mysql-query-optimization",
        "star-conflict",
    ]
    brief = data(await call(agent, token, "prepare_prep_topics", {"job_id": weak}))
    assert [topic["slug"] for topic in brief["topics"]] == [
        "mysql-query-optimization",
        "star-conflict",
    ]


async def test_an_invalid_topic_is_a_tool_error_and_saves_nothing(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)

    result = await call(
        agent,
        token,
        "save_prep_topics",
        {"job_id": number, "topics": [MYSQL, {**STAR, "slug": "Star_Conflict"}]},
    )

    assert (
        "slug 'Star_Conflict': латиниця в нижньому регістрі, цифри й дефіси між словами, "
        "2–60 символів (напр. mysql-query-optimization)."
    ) in error_text(result)
    assert data(await call(agent, token, "list_prep_topics")) == {"topics": []}


async def test_a_kind_outside_the_schema_is_rejected(agent: Agent) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)
    result = await call(
        agent,
        token,
        "save_prep_topics",
        {"job_id": number, "topics": [{**MYSQL, "kind": "soft"}]},
    )
    assert "behavioral" in error_text(result)


async def test_a_user_does_not_see_or_change_another_users_topics(
    agent: Agent,
) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    mine = await analysed(agent, taras_token, 82)
    await save(agent, taras_token, mine, MYSQL)
    hers = await analysed(agent, katya_token, 20, who="katya@example.com")

    assert data(await call(agent, katya_token, "list_prep_topics")) == {"topics": []}
    saved = await save(agent, katya_token, hers, {**MYSQL, "title": "Олина тема"})

    topic = only(saved["topics"])
    assert (topic["topic_id"], topic["title"], topic["priority"]) == (
        1,
        "Олина тема",
        20,
    )
    kept = only(data(await call(agent, taras_token, "list_prep_topics"))["topics"])
    assert (kept["title"], kept["priority"]) == ("Оптимізація запитів MySQL", 82)
