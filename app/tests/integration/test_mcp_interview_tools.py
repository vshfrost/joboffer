"""Тули пакета до інтерв'ю через SDK-клієнт: DCR → токен → `tools/list` і виклики на справжньому
Postgres."""

from datetime import UTC, datetime
from typing import Any

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from domain.shared.local_time import local_day
from tests.integration.test_agent_http import PUBLIC, Agent
from tests.integration.test_mcp_analysis_tools import add_fact, seed
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

NAMES = ("prepare_interview_kit", "save_interview_kit")


def question(
    n: int, kind: str = "technical", topic: int | None = None
) -> dict[str, Any]:
    return {"kind": kind, "question": f"Question {n}?", "topic_id": topic}


def story(n: int, *facts: int, title: str | None = None) -> dict[str, Any]:
    return {
        "title": title or f"Story {n}",
        "situation": f"Situation {n}",
        "task": f"Task {n}",
        "action": f"Action {n}",
        "result": f"Result {n}",
        "fact_ids": list(facts),
    }


def kit(fact: int, topic: int | None = None, tag: str = "") -> dict[str, Any]:
    return {
        "questions": [
            {**question(n, topic=topic if n == 1 else None), "question": f"{tag}Q{n}?"}
            for n in range(1, 6)
        ],
        "stories": [story(n, fact) for n in range(1, 4)],
        "company_questions": [f"{tag}Ask {n}?" for n in range(1, 4)],
    }


async def confirmed_fact(agent: Agent, token: str, text: str = "Python") -> int:
    fact = await add_fact(agent, token, "skill", text)
    data(await call(agent, token, "confirm_facts", {"fact_ids": [fact]}))
    return fact


async def save_kit(
    agent: Agent, token: str, job: int, content: dict[str, Any]
) -> dict[str, Any]:
    return data(
        await call(agent, token, "save_interview_kit", {"job_id": job} | content)
    )


async def test_tools_list_has_both_interview_kit_tools_with_the_catalog_descriptions(
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


async def test_the_brief_has_the_job_analysis_topics_confirmed_facts_and_rules(
    agent: Agent,
) -> None:
    token = await taras(agent)
    job = await analysed(agent, token, 82)
    saved = await save(agent, token, job, MYSQL, STAR)
    mysql, star = (t["topic_id"] for t in saved["topics"])
    first = await confirmed_fact(agent, token, "Python")
    await add_fact(agent, token, "skill", "Unconfirmed")
    second = await confirmed_fact(agent, token, "Postgres")

    brief = data(await call(agent, token, "prepare_interview_kit", {"job_id": job}))

    assert brief["job"]["job_id"] == job
    assert brief["analysis"]["score"] == 82
    assert [t["topic_id"] for t in brief["topics"]] == [mysql, star]
    assert [f["fact_id"] for f in brief["confirmed_facts"]] == [first, second]
    assert brief["previous"] is None
    assert brief["rules"].startswith(
        "Prepare the user's interview kit for this job, in English."
    )
    assert "Taras" not in brief["rules"]


async def test_the_analysis_is_not_required(agent: Agent) -> None:
    token = await taras(agent)
    job = await seed(agent, "Senior Python engineer. Remote.")

    brief = data(await call(agent, token, "prepare_interview_kit", {"job_id": job}))

    assert brief["analysis"] is None
    assert brief["topics"] == []
    assert brief["confirmed_facts"] == []


async def test_a_saved_kit_comes_back_whole_with_the_madrid_day_of_creation(
    agent: Agent,
) -> None:
    token = await taras(agent)
    job = await analysed(agent, token, 82)
    topic = (await save(agent, token, job, MYSQL))["topics"][0]["topic_id"]
    fact = await confirmed_fact(agent, token)

    before = local_day(datetime.now(UTC))
    saved = await save_kit(agent, token, job, kit(fact, topic))
    after = local_day(datetime.now(UTC))

    assert saved["created"] in {before, after}
    assert {k: v for k, v in saved.items() if k != "created"} == {
        "kit_id": 1,
        "job_id": job,
        "version": 1,
        "questions": [
            {"kind": "technical", "question": "Q1?", "topic_id": topic},
            *(
                {"kind": "technical", "question": f"Q{n}?", "topic_id": None}
                for n in range(2, 6)
            ),
        ],
        "stories": [
            {
                "title": f"Story {n}",
                "situation": f"Situation {n}",
                "task": f"Task {n}",
                "action": f"Action {n}",
                "result": f"Result {n}",
                "fact_ids": [fact],
            }
            for n in range(1, 4)
        ],
        "company_questions": ["Ask 1?", "Ask 2?", "Ask 3?"],
    }


async def test_every_save_is_a_new_version_and_the_brief_shows_the_last_one(
    agent: Agent,
) -> None:
    token = await taras(agent)
    job = await analysed(agent, token, 82)
    fact = await confirmed_fact(agent, token)

    first = await save_kit(agent, token, job, kit(fact))
    second = await save_kit(agent, token, job, kit(fact, tag="New "))
    brief = data(await call(agent, token, "prepare_interview_kit", {"job_id": job}))

    assert (first["version"], second["version"]) == (1, 2)
    assert (first["kit_id"], second["kit_id"]) == (1, 2)
    assert brief["previous"] == second
    assert brief["previous"]["questions"][0]["question"] == "New Q1?"


async def test_versions_are_counted_per_job(agent: Agent) -> None:
    token = await taras(agent)
    first_job = await analysed(agent, token, 82)
    second_job = await analysed(agent, token, 70)
    fact = await confirmed_fact(agent, token)

    await save_kit(agent, token, first_job, kit(fact))
    other = await save_kit(agent, token, second_job, kit(fact))

    assert (other["job_id"], other["version"], other["kit_id"]) == (second_job, 1, 2)


async def test_a_rejected_kit_is_a_tool_error_and_nothing_is_saved(
    agent: Agent,
) -> None:
    token = await taras(agent)
    job = await analysed(agent, token, 82)
    fact = await confirmed_fact(agent, token)
    unconfirmed = await add_fact(agent, token, "skill", "Unconfirmed")

    def attempt(**changes: Any) -> Any:
        return call(
            agent, token, "save_interview_kit", {"job_id": job} | kit(fact) | changes
        )

    few = await attempt(questions=[question(n) for n in range(1, 5)])
    bad_question = await attempt(
        questions=[question(1), {**question(2), "question": "q" * 501}]
        + [question(n) for n in range(3, 6)]
    )
    bad_story = await attempt(
        stories=[story(1, fact), story(2, fact, title="t" * 121), story(3, fact)]
    )
    bad_company = await attempt(company_questions=["A?", "", "C?"])
    ghost = await attempt(
        stories=[story(n, fact if n > 1 else 99) for n in range(1, 4)]
    )
    loose = await attempt(
        stories=[story(n, fact if n > 1 else unconfirmed) for n in range(1, 4)]
    )
    stray = await attempt(questions=[question(n, topic=9) for n in range(1, 6)])

    assert "questions: 4 — треба від 5 до 20." in error_text(few)
    assert "Питання 2: питання — від 1 до 500 символів." in error_text(bad_question)
    assert "Історія 2: назва — від 1 до 120 символів." in error_text(bad_story)
    assert "Питання до компанії 2: питання до компанії — від 1 до 500 символів." in (
        error_text(bad_company)
    )
    assert "Факти не знайдено: #99." in error_text(ghost)
    assert f"Факти не підтверджені: #{unconfirmed}" in error_text(loose)
    assert "Теми не знайдено: 9." in error_text(stray)
    brief = data(await call(agent, token, "prepare_interview_kit", {"job_id": job}))
    assert brief["previous"] is None


async def test_a_missing_or_foreign_job_is_a_tool_error(agent: Agent) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    job = await analysed(agent, taras_token, 82)
    fact = await confirmed_fact(agent, taras_token)
    await save_kit(agent, taras_token, job, kit(fact))

    for name, arguments in (
        ("prepare_interview_kit", {"job_id": job}),
        ("save_interview_kit", {"job_id": job} | kit(1)),
        ("prepare_interview_kit", {"job_id": 99}),
    ):
        result = await call(agent, katya_token, name, arguments)
        assert f"Вакансію {arguments['job_id']} не знайдено." in error_text(result), (
            name
        )
    mine = data(
        await call(agent, taras_token, "prepare_interview_kit", {"job_id": job})
    )
    assert mine["previous"]["version"] == 1


async def test_the_brief_never_shows_a_foreign_fact_or_kit(agent: Agent) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    job = await analysed(agent, taras_token, 82)
    await confirmed_fact(agent, taras_token, "Secret")
    own_job = await analysed(agent, katya_token, 70, who="katya@example.com")

    brief = data(
        await call(agent, katya_token, "prepare_interview_kit", {"job_id": own_job})
    )

    assert job == own_job == 1
    assert brief["confirmed_facts"] == []
    assert brief["previous"] is None
