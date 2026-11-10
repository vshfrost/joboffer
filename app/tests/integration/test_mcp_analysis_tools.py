"""Тули аналізу через SDK-клієнт: DCR → токен → `tools/list` і виклики на справжньому Postgres."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import text

from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.shared.local_time import local_day
from tests.integration.test_agent_http import PUBLIC, Agent
from tests.integration.test_mcp_job_tools import data, error_text, listed
from tests.integration.test_mcp_profile_tools import (
    FULL,
    TOOLS,
    agent,
    anyio_backend,
    call,
    katya,
    taras,
    update_profile,
)

__all__ = ["agent", "anyio_backend"]

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
ALL_FIELDS: dict[str, Any] = {
    "score": 82,
    "summary": "A backend role.",
    "must_have": ["Python", "Postgres"],
    "nice_to_have": ["Go"],
    "keywords": ["asyncio"],
    "seniority": "senior",
    "work_mode": "remote",
    "location": "Madrid",
    "languages": ["English"],
    "salary_min_eur": 60000,
    "salary_max_eur": 80000,
    "relocation": True,
    "reasons": ["Fits", "Remote"],
    "candidate_asks": ["Send your GitHub", "Skip the list of frameworks"],
    "gaps": [
        {"gap": "No Go", "question": "Do you have Go experience? Where, how long?"}
    ],
}
NUMBERED_GAPS = [
    {
        "number": 1,
        "gap": "No Go",
        "question": "Do you have Go experience? Where, how long?",
    }
]


async def seed(
    agent: Agent,
    body: str | None = "Senior Python engineer. Remote.",
    *,
    who: str = "taras@example.com",
    minutes: int = 0,
    title: str | None = "Backend",
    company: str | None = "Acme",
) -> int:
    async with agent.container.unit_of_work() as tx:
        number = await tx.jobs.add(
            UserId.parse(agent.user_ids[who]),
            JobId(uuid4()),
            NewJob(text=body, title=title, company=company),
            NOW + timedelta(minutes=minutes),
        )
        await tx.commit()
        return number


async def add_fact(agent: Agent, token: str, kind: str, text: str) -> int:
    saved = data(
        await call(
            agent, token, "save_facts", {"facts": [{"kind": kind, "text": text}]}
        )
    )
    return int(saved["added"][0]["fact_id"])


async def save(agent: Agent, token: str, job_id: int, **fields: Any) -> dict[str, Any]:
    arguments = {"job_id": job_id, "analysis": {"score": 70, "summary": "S."} | fields}
    return data(await call(agent, token, "save_analysis", arguments))


async def test_save_analysis_refuses_a_fact_id_that_does_not_exist_in_the_fact_map(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)
    arguments = {
        "job_id": number,
        "analysis": {
            "score": 50,
            "summary": "S.",
            "keywords": ["Kafka"],
            "keyword_facts": {"Kafka": [99]},
        },
    }

    refused = await call(agent, token, "save_analysis", arguments)

    assert "Факти не знайдено: #99." in error_text(refused)


async def test_tools_list_has_both_analysis_tools_with_the_catalog_descriptions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    for name in ("prepare_analysis", "save_analysis"):
        assert tools[name].description == (TOOLS / f"{name}.md").read_text(
            encoding="utf-8"
        )


async def test_the_brief_has_the_job_profile_confirmed_facts_and_the_rubric(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await update_profile(agent, token, FULL)
    number = await seed(agent, "Go role.", title="Go Dev", company="Acme")
    confirmed = await add_fact(agent, token, "skill", "Python")
    await add_fact(agent, token, "skill", "Rust")
    await call(agent, token, "confirm_facts", {"fact_ids": [confirmed]})

    brief = data(await call(agent, token, "prepare_analysis", {"job_id": number}))

    assert brief["job"]["job_id"] == number
    assert brief["job"]["untrusted_job_text"] == "Go role."
    assert brief["profile"] == FULL
    assert brief["confirmed_facts"] == [
        {"fact_id": confirmed, "kind": "skill", "text": "Python", "confirmed": True}
    ]
    assert "how well the job fits Test User" in brief["rubric"]
    assert "(e.g. fintech, payments)" in brief["rubric"]
    assert "{" not in brief["rubric"]
    assert brief["previous"] is None


async def test_the_rubric_for_an_empty_profile_is_neutral(agent: Agent) -> None:
    token = await taras(agent)
    number = await seed(agent)
    brief = data(await call(agent, token, "prepare_analysis", {"job_id": number}))
    assert "how well the job fits the candidate" in brief["rubric"]
    assert "(e.g." not in brief["rubric"]
    assert "{" not in brief["rubric"]


async def test_a_missing_job_and_a_job_without_text_are_tool_errors(
    agent: Agent,
) -> None:
    token = await taras(agent)
    missing = await call(agent, token, "prepare_analysis", {"job_id": 7})
    assert "Вакансію 7 не знайдено." in error_text(missing)
    waiting = await seed(agent, None)
    refused = await call(agent, token, "prepare_analysis", {"job_id": waiting})
    assert (
        f"У вакансії {waiting} нема тексту опису (вона з листа-алерту): спершу додай текст."
        in error_text(refused)
    )


async def test_save_returns_every_field_and_the_flags(agent: Agent) -> None:
    token = await taras(agent)
    number = await seed(agent)
    saved = await save(agent, token, number, **ALL_FIELDS)
    assert saved.pop("updated") == local_day(datetime.now(UTC))
    assert saved == {
        **ALL_FIELDS,
        "gaps": NUMBERED_GAPS,
        "job_id": number,
        "filters_passed": True,
        "flags": [],
    }


async def test_candidate_asks_are_saved_and_shown_as_the_previous_analysis_of_the_brief(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)
    asks = ["Send your GitHub", "Describe a project you are proud of"]

    saved = await save(agent, token, number, candidate_asks=asks)
    brief = data(await call(agent, token, "prepare_analysis", {"job_id": number}))

    assert saved["candidate_asks"] == asks
    assert brief["previous"]["candidate_asks"] == asks


async def test_an_analysis_saved_without_candidate_asks_returns_an_empty_list(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)

    saved = await save(agent, token, number)

    assert saved["candidate_asks"] == []


async def test_too_many_candidate_asks_are_a_tool_error_and_save_nothing(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)

    refused = await call(
        agent,
        token,
        "save_analysis",
        {
            "job_id": number,
            "analysis": {
                "score": 70,
                "summary": "S.",
                "candidate_asks": [f"ask {n}" for n in range(31)],
            },
        },
    )

    assert "candidate_asks — не більше 30 пунктів." in error_text(refused)


async def confirmed_fact(agent: Agent, token: str, text: str) -> int:
    fact = await add_fact(agent, token, "skill", text)
    data(await call(agent, token, "confirm_facts", {"fact_ids": [fact]}))
    return fact


async def test_gap_analogues_are_saved_and_a_gap_without_them_has_no_honest_analogue(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)
    rest = await confirmed_fact(agent, token, "REST")

    await save(
        agent,
        token,
        number,
        gaps=["gRPC", "OpenTelemetry"],
        gap_analogues=[
            {
                "gap": "gRPC",
                "analogues": [{"fact_ids": [rest], "explanation": "REST services"}],
            }
        ],
    )
    brief = data(await call(agent, token, "prepare_analysis", {"job_id": number}))

    assert brief["previous"]["gap_analogues"] == [
        {
            "gap": "gRPC",
            "analogues": [{"fact_ids": [rest], "explanation": "REST services"}],
            "no_honest_analogue": False,
        },
        {"gap": "OpenTelemetry", "analogues": [], "no_honest_analogue": True},
    ]


async def test_an_analysis_saved_without_gap_analogues_shows_null_in_the_brief(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)

    await save(agent, token, number, gaps=["gRPC"])
    brief = data(await call(agent, token, "prepare_analysis", {"job_id": number}))

    assert brief["previous"]["gap_analogues"] is None


async def test_an_unconfirmed_fact_in_gap_analogues_is_a_tool_error_and_saves_nothing(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)
    draft = await add_fact(agent, token, "skill", "REST")

    refused = await call(
        agent,
        token,
        "save_analysis",
        {
            "job_id": number,
            "analysis": {
                "score": 70,
                "summary": "S.",
                "gaps": ["gRPC"],
                "gap_analogues": [
                    {
                        "gap": "gRPC",
                        "analogues": [
                            {"fact_ids": [draft], "explanation": "REST services"}
                        ],
                    }
                ],
            },
        },
    )

    assert f"Факти не підтверджені: #{draft}" in error_text(refused)
    brief = data(await call(agent, token, "prepare_analysis", {"job_id": number}))
    assert brief["previous"] is None


async def test_a_fact_of_another_user_in_gap_analogues_is_a_tool_error(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)
    theirs = await confirmed_fact(agent, await katya(agent), "REST")

    refused = await call(
        agent,
        token,
        "save_analysis",
        {
            "job_id": number,
            "analysis": {
                "score": 70,
                "summary": "S.",
                "gaps": ["gRPC"],
                "gap_analogues": [
                    {
                        "gap": "gRPC",
                        "analogues": [
                            {"fact_ids": [theirs], "explanation": "REST services"}
                        ],
                    }
                ],
            },
        },
    )

    assert f"Факти не знайдено: #{theirs}." in error_text(refused)


async def test_gap_analogues_of_a_gap_that_is_not_in_gaps_are_a_tool_error(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)

    refused = await call(
        agent,
        token,
        "save_analysis",
        {
            "job_id": number,
            "analysis": {
                "score": 70,
                "summary": "S.",
                "gaps": ["gRPC"],
                "gap_analogues": [{"gap": "Rust", "analogues": []}],
            },
        },
    )

    assert "gap_analogues: «Rust» — такої прогалини нема в gaps." in error_text(refused)


async def test_the_rubric_asks_for_one_question_for_every_gap(agent: Agent) -> None:
    token = await taras(agent)
    number = await seed(agent)
    brief = data(await call(agent, token, "prepare_analysis", {"job_id": number}))
    assert "one short question for every gap" in brief["rubric"]


async def test_gaps_with_questions_come_back_numbered_from_1(agent: Agent) -> None:
    token = await taras(agent)
    number = await seed(agent)
    saved = await save(
        agent,
        token,
        number,
        gaps=[
            {"gap": "Kubernetes", "question": "Have you run Kubernetes? Where?"},
            {"gap": "Go", "question": "Have you written Go? How long?"},
        ],
    )
    expected = [
        {
            "number": 1,
            "gap": "Kubernetes",
            "question": "Have you run Kubernetes? Where?",
        },
        {"number": 2, "gap": "Go", "question": "Have you written Go? How long?"},
    ]
    assert saved["gaps"] == expected
    brief = data(await call(agent, token, "prepare_analysis", {"job_id": number}))
    assert brief["previous"]["gaps"] == expected


async def test_the_old_format_of_gaps_is_accepted_and_has_no_questions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)
    saved = await save(agent, token, number, gaps=["Kubernetes", "Go"])
    assert saved["gaps"] == [
        {"number": 1, "gap": "Kubernetes", "question": None},
        {"number": 2, "gap": "Go", "question": None},
    ]


async def test_an_analysis_stored_with_string_gaps_is_read_with_null_questions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)
    await save(agent, token, number)
    async with agent.container.engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE job_analyses SET details = jsonb_set(details, '{gaps}', "
                '\'["Old gap", "Another"]\'::jsonb)'
            )
        )
    brief = data(await call(agent, token, "prepare_analysis", {"job_id": number}))
    assert brief["previous"]["gaps"] == [
        {"number": 1, "gap": "Old gap", "question": None},
        {"number": 2, "gap": "Another", "question": None},
    ]


async def test_a_repeated_save_replaces_the_gaps(agent: Agent) -> None:
    token = await taras(agent)
    number = await seed(agent)
    await save(agent, token, number, gaps=[{"gap": "Go", "question": "Go?"}])
    saved = await save(
        agent, token, number, gaps=[{"gap": "Rust", "question": "Rust?"}]
    )
    assert saved["gaps"] == [{"number": 1, "gap": "Rust", "question": "Rust?"}]
    brief = data(await call(agent, token, "prepare_analysis", {"job_id": number}))
    assert brief["previous"]["gaps"] == saved["gaps"]


async def test_an_analysis_without_gaps_is_saved(agent: Agent) -> None:
    token = await taras(agent)
    number = await seed(agent)
    assert (await save(agent, token, number, gaps=[]))["gaps"] == []


@pytest.mark.parametrize(
    ("gaps", "message"),
    [
        ([{"gap": "Go"}], "gaps: у прогалини 1 нема питання."),
        (
            [{"gap": "Go", "question": "Go?"}, {"gap": "Rust", "question": ""}],
            "gaps: у прогалини 2 нема питання.",
        ),
        (
            [{"gap": "Go", "question": "q" * 301}],
            "gaps: питання прогалини 1 довше за 300 символів.",
        ),
    ],
)
async def test_a_gap_without_a_question_or_with_a_long_one_is_refused_by_number(
    agent: Agent, gaps: list[dict[str, str]], message: str
) -> None:
    token = await taras(agent)
    number = await seed(agent)
    result = await call(
        agent,
        token,
        "save_analysis",
        {"job_id": number, "analysis": {"score": 50, "summary": "S.", "gaps": gaps}},
    )
    assert message in error_text(result)
    [job] = data(await call(agent, token, "list_jobs"))["jobs"]
    assert job["score"] is None


async def test_the_hard_filters_of_the_profile_become_flags(agent: Agent) -> None:
    token = await taras(agent)
    await update_profile(
        agent, token, {**FULL, "stop_words": ["python"], "work_modes": ["hybrid"]}
    )
    number = await seed(agent)
    saved = await save(agent, token, number, work_mode="onsite", seniority="junior")
    assert saved["filters_passed"] is False
    assert saved["flags"] == [
        "Формат onsite — не з профілю.",
        "Рівень junior — не з профілю.",
        "Стоп-слово: python.",
    ]


async def test_the_brief_shows_the_previous_analysis_and_save_replaces_it(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)
    await save(agent, token, number, score=30, summary="First.")
    brief = data(await call(agent, token, "prepare_analysis", {"job_id": number}))
    assert (brief["previous"]["score"], brief["previous"]["summary"]) == (30, "First.")
    await save(agent, token, number, score=90, summary="Second.")
    [job] = data(await call(agent, token, "list_jobs"))["jobs"]
    assert job["score"] == 90


async def test_an_invalid_analysis_is_a_tool_error_and_saves_nothing(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number = await seed(agent)
    result = await call(
        agent,
        token,
        "save_analysis",
        {"job_id": number, "analysis": {"score": 50, "summary": "  "}},
    )
    assert "summary — від 1 до 1000 символів." in error_text(result)
    bad_range = await call(
        agent,
        token,
        "save_analysis",
        {
            "job_id": number,
            "analysis": {
                "score": 50,
                "summary": "S.",
                "salary_min_eur": 9,
                "salary_max_eur": 5,
            },
        },
    )
    assert "salary_min_eur більша за salary_max_eur." in error_text(bad_range)
    [job] = data(await call(agent, token, "list_jobs"))["jobs"]
    assert job["score"] is None


async def test_a_score_outside_0_to_100_is_rejected_by_the_schema(agent: Agent) -> None:
    token = await taras(agent)
    number = await seed(agent)
    result = await call(
        agent,
        token,
        "save_analysis",
        {"job_id": number, "analysis": {"score": 101, "summary": "S."}},
    )
    assert result.is_error is True


async def test_saving_for_a_missing_job_is_a_tool_error(agent: Agent) -> None:
    token = await taras(agent)
    result = await call(
        agent,
        token,
        "save_analysis",
        {"job_id": 5, "analysis": {"score": 1, "summary": "S."}},
    )
    assert "Вакансію 5 не знайдено." in error_text(result)


async def test_the_list_has_score_filters_work_mode_and_the_work_mode_filter(
    agent: Agent,
) -> None:
    token = await taras(agent)
    remote = await seed(agent, "one", minutes=0)
    onsite = await seed(agent, "two", minutes=1)
    plain = await seed(agent, "three", minutes=2)
    await save(agent, token, remote, score=60, work_mode="remote")
    await save(agent, token, onsite, score=0, work_mode="onsite")
    jobs = data(await call(agent, token, "list_jobs"))["jobs"]
    assert [
        (j["job_id"], j["score"], j["filters_passed"], j["work_mode"]) for j in jobs
    ] == [
        (remote, 60, True, "remote"),
        (onsite, 0, True, "onsite"),
        (plain, None, None, None),
    ]
    assert await listed(agent, token, filters={"work_mode": "remote"}) == [remote]


async def test_an_analysed_job_is_no_longer_triaged(agent: Agent) -> None:
    token = await taras(agent)
    analysed = await seed(agent, "one", minutes=0)
    waiting = await seed(agent, "two", minutes=1)
    await save(agent, token, analysed)
    brief = data(await call(agent, token, "prepare_triage"))
    assert [job["job_id"] for job in brief["jobs"]] == [waiting]
    result = await call(
        agent,
        token,
        "save_triage",
        {
            "items": [
                {"job_id": analysed, "score": 50, "verdict": "maybe", "reason": "r"}
            ]
        },
    )
    assert f"Елемент 1: вакансію {analysed} уже проаналізовано." in error_text(result)


async def test_a_user_does_not_see_or_overwrite_the_analysis_of_another(
    agent: Agent,
) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    await seed(agent, "filler")
    mine = await seed(agent, "mine")
    theirs = await seed(agent, "theirs", who="katya@example.com")
    await save(agent, taras_token, mine, score=88)

    stolen = await call(
        agent,
        katya_token,
        "save_analysis",
        {"job_id": mine, "analysis": {"score": 1, "summary": "S."}},
    )
    assert f"Вакансію {mine} не знайдено." in error_text(stolen)
    peek = await call(agent, katya_token, "prepare_analysis", {"job_id": mine})
    assert peek.is_error is True
    [job] = data(await call(agent, katya_token, "list_jobs"))["jobs"]
    assert (job["job_id"], job["score"]) == (theirs, None)
