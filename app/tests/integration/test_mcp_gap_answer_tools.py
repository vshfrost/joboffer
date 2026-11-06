"""`answer_gap` через SDK-клієнт: DCR → токен → виклики на справжньому Postgres."""

from datetime import UTC, datetime
from typing import Any

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import text

from domain.shared.local_time import local_day
from tests.integration.test_agent_http import PUBLIC, Agent
from tests.integration.test_mcp_analysis_tools import save, seed
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

GAPS = [
    {"gap": "No Go", "question": "Do you have Go experience? Where, how long?"},
    {"gap": "No Kubernetes", "question": "Have you run Kubernetes?"},
]
GO_FACT = {"kind": "experience", "text": "2 years of Go at Acme"}


async def analysed(agent: Agent, token: str, **kwargs: Any) -> int:
    number = await seed(agent, **kwargs)
    await save(agent, token, number, gaps=GAPS)
    return number


async def answer(
    agent: Agent,
    token: str,
    job_id: int,
    gap_number: int,
    has_experience: bool,
    facts: list[dict[str, str]] | None = None,
) -> Any:
    arguments: dict[str, Any] = {
        "job_id": job_id,
        "gap_number": gap_number,
        "has_experience": has_experience,
    }
    if facts is not None:
        arguments["facts"] = facts
    return await call(agent, token, "answer_gap", arguments)


async def inputs_changed_at(agent: Agent) -> object:
    async with agent.container.engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT analysis_inputs_changed_at FROM profiles")
        )
        return rows.scalar_one_or_none()


async def brief(agent: Agent, token: str, job_id: int) -> dict[str, Any]:
    return data(await call(agent, token, "prepare_analysis", {"job_id": job_id}))


async def test_tools_list_has_answer_gap_with_the_catalog_description(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert tools["answer_gap"].description == (TOOLS / "answer_gap.md").read_text(
        encoding="utf-8"
    )


async def test_experience_saves_the_chat_fact_and_closes_the_gap(agent: Agent) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)

    result = data(await answer(agent, token, number, 1, True, [GO_FACT]))

    fact_id = result["fact_ids"][0]
    assert result == {
        "job_id": number,
        "gap_number": 1,
        "gap": "No Go",
        "has_experience": True,
        "closed": True,
        "fact_ids": [fact_id],
        "facts": [
            {
                "fact_id": fact_id,
                "kind": "experience",
                "text": "2 years of Go at Acme",
                "confirmed": True,
                "source": "chat",
                "job_id": number,
            }
        ],
    }
    listed = data(await call(agent, token, "list_facts"))
    assert [
        (f["fact_id"], f["source"], f["confirmed"], f["job_id"])
        for f in listed["facts"]
    ] == [(fact_id, "chat", True, number)]


async def test_experience_makes_the_analysis_stale(agent: Agent) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)
    assert await inputs_changed_at(agent) is None

    await answer(agent, token, number, 1, True, [GO_FACT])

    assert await inputs_changed_at(agent) is not None


async def test_no_experience_is_stored_and_the_analysis_stays_fresh(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)

    result = data(await answer(agent, token, number, 2, False))

    assert result == {
        "job_id": number,
        "gap_number": 2,
        "gap": "No Kubernetes",
        "has_experience": False,
        "closed": False,
        "fact_ids": [],
        "facts": [],
    }
    assert await inputs_changed_at(agent) is None
    assert data(await call(agent, token, "list_facts"))["facts"] == []


async def test_experience_without_facts_is_a_tool_error(agent: Agent) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)

    cases: list[list[dict[str, str]] | None] = [None, []]
    for facts in cases:
        refused = await answer(agent, token, number, 1, True, facts)
        assert "Відповідь «є досвід» потребує хоча б одного факту" in error_text(
            refused
        )

    assert (await brief(agent, token, number))["gap_answers"] == []


async def test_no_experience_with_facts_is_a_tool_error(agent: Agent) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)
    refused = await answer(agent, token, number, 1, False, [GO_FACT])
    assert "Відповідь «немає досвіду» не може мати фактів." in error_text(refused)


async def test_a_missing_job_or_gap_is_a_tool_error(agent: Agent) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)

    assert "Вакансію 99 не знайдено." in error_text(
        await answer(agent, token, 99, 1, False)
    )
    assert f"Прогалину 5 вакансії {number} не знайдено." in error_text(
        await answer(agent, token, number, 5, False)
    )
    assert f"Прогалину 0 вакансії {number} не знайдено." in error_text(
        await answer(agent, token, number, 0, False)
    )


async def test_a_job_without_an_analysis_is_a_tool_error(agent: Agent) -> None:
    token = await taras(agent)
    number = await seed(agent)
    assert f"Аналіз вакансії {number} не знайдено." in error_text(
        await answer(agent, token, number, 1, False)
    )


async def test_another_users_job_is_not_found_and_nothing_changes(
    agent: Agent,
) -> None:
    mine = await taras(agent)
    theirs = await katya(agent)
    number = await analysed(agent, mine)

    refused = await answer(agent, theirs, number, 1, True, [GO_FACT])

    assert f"Вакансію {number} не знайдено." in error_text(refused)
    assert (await brief(agent, mine, number))["gap_answers"] == []
    assert data(await call(agent, mine, "list_facts"))["facts"] == []
    assert await inputs_changed_at(agent) is None


async def test_a_duplicate_fact_is_not_created_and_the_existing_one_is_linked(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)
    saved = data(
        await call(agent, token, "save_facts", {"facts": [GO_FACT], "source": "cv"})
    )
    existing = saved["added"][0]["fact_id"]

    result = data(
        await answer(
            agent,
            token,
            number,
            1,
            True,
            [{"kind": "skill", "text": "2 YEARS of Go  at Acme"}],
        )
    )

    assert result["fact_ids"] == [existing]
    listed = data(await call(agent, token, "list_facts"))["facts"]
    assert [(f["fact_id"], f["source"], f["confirmed"]) for f in listed] == [
        (existing, "cv", True)
    ]


async def test_a_repeated_answer_replaces_the_previous_one(agent: Agent) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)
    await answer(agent, token, number, 1, True, [GO_FACT])

    await answer(agent, token, number, 1, False)

    assert (await brief(agent, token, number))["gap_answers"] == [
        {
            "gap": "No Go",
            "has_experience": False,
            "fact_ids": [],
            "answered": local_day(datetime.now(UTC)),
        }
    ]


async def test_reanalysis_with_the_same_gap_shows_the_no_answer(agent: Agent) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)
    await answer(agent, token, number, 2, False)

    await save(
        agent,
        token,
        number,
        summary="Updated.",
        gaps=[{"gap": "No Kubernetes", "question": "Have you run Kubernetes?"}],
    )

    stored = (await brief(agent, token, number))["gap_answers"]
    assert [(a["gap"], a["has_experience"]) for a in stored] == [
        ("No Kubernetes", False)
    ]


async def test_the_brief_of_another_user_has_no_answers(agent: Agent) -> None:
    mine = await taras(agent)
    number = await analysed(agent, mine)
    await answer(agent, mine, number, 1, False)

    theirs = await katya(agent)
    other = await seed(agent, who="katya@example.com")
    await save(agent, theirs, other, gaps=GAPS)

    assert (await brief(agent, theirs, other))["gap_answers"] == []
