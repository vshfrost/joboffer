"""Тули тріажу через SDK-клієнт: DCR → токен → `tools/list` і виклики на справжньому Postgres."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from domain.applications.application import (
    ApplicationChannel,
    ApplicationStatus,
    NewApplication,
)
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.triage.ids import TriageId
from domain.triage.triage import TriageEntry, TriageVerdict
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


async def seed(
    agent: Agent,
    body: str | None = "Senior Python engineer. Remote.",
    *,
    who: str = "taras@example.com",
    minutes: int = 0,
    title: str | None = None,
    company: str | None = None,
    url: str | None = None,
    linkedin_id: str | None = None,
    location: str | None = None,
    source: str = "manual",
) -> int:
    job = NewJob(
        text=body,
        title=title,
        company=company,
        url=url,
        linkedin_id=linkedin_id,
        location=location,
        source=source,
    )
    async with agent.container.unit_of_work() as tx:
        number = await tx.jobs.add(
            UserId.parse(agent.user_ids[who]),
            JobId(uuid4()),
            job,
            NOW + timedelta(minutes=minutes),
        )
        await tx.commit()
        return number


async def close_application(
    agent: Agent, number: int, status: ApplicationStatus, who: str = "taras@example.com"
) -> None:
    user = UserId.parse(agent.user_ids[who])
    async with agent.container.unit_of_work() as tx:
        await tx.applications.save(
            user,
            number,
            NewApplication(
                applied_on=date(2026, 1, 1), channel=ApplicationChannel.EMAIL
            ),
            NOW,
        )
        await tx.applications.set_status(user, number, status, NOW)
        await tx.commit()


async def rate_by_rules(agent: Agent, number: int, verdict: TriageVerdict) -> None:
    user = UserId.parse(agent.user_ids["taras@example.com"])
    async with agent.container.unit_of_work() as tx:
        job = await tx.jobs.get(user, number)
        assert job is not None
        await tx.triage.save_auto(
            user,
            [
                (
                    TriageId(uuid4()),
                    job.id,
                    TriageEntry(number, 50, verdict, "Rules"),
                    "hash",
                )
            ],
            NOW,
        )
        await tx.commit()


def item(
    job_id: int, score: int = 70, verdict: str = "maybe", reason: str = "ok"
) -> dict[str, Any]:
    return {"job_id": job_id, "score": score, "verdict": verdict, "reason": reason}


async def test_tools_list_has_both_triage_tools_with_the_catalog_descriptions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    for name in ("prepare_triage", "save_triage"):
        assert tools[name].description == (TOOLS / f"{name}.md").read_text(
            encoding="utf-8"
        )


async def test_an_empty_brief_says_nothing_is_pending(agent: Agent) -> None:
    brief = data(await call(agent, await taras(agent), "prepare_triage"))
    assert (brief["jobs"], brief["pending"]) == ([], 0)


async def test_the_brief_has_the_texts_the_profile_the_rules_and_the_facts(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await update_profile(agent, token, FULL)
    older = await seed(agent, "x" * 1600, minutes=0, title="Old", location="Berlin")
    newer = await seed(
        agent, "Go role", minutes=1, title="Go Dev", company="Acme", source="rss:dou"
    )

    await call(
        agent,
        token,
        "save_facts",
        {"facts": [{"kind": "skill", "text": "Python"}], "source": "manual"},
    )
    await call(agent, token, "confirm_facts", {"fact_ids": [1]})
    await call(
        agent,
        token,
        "save_facts",
        {"facts": [{"kind": "skill", "text": "Unconfirmed Rust"}]},
    )

    brief = data(await call(agent, token, "prepare_triage", {"limit": 5}))

    assert [job["job_id"] for job in brief["jobs"]] == [newer, older]
    first, second = brief["jobs"]
    assert first == {
        "job_id": newer,
        "title": "Go Dev",
        "company": "Acme",
        "source": "rss:dou",
        "job_location": None,
        "untrusted_job_text": "Go role",
        "text_scope": "full",
    }
    assert second["untrusted_job_text"] == "x" * 1600
    assert second["job_location"] == "Berlin"
    assert brief["pending"] == 2
    assert brief["facts"] == [{"kind": "skill", "text": "Python"}]
    assert brief["profile"] == FULL
    assert brief["rules"] == (TOOLS.parent.parent / "triage" / "rules.md").read_text(
        encoding="utf-8"
    )


async def test_the_brief_limit_is_cut_but_pending_counts_all(agent: Agent) -> None:
    token = await taras(agent)
    for index in range(3):
        await seed(agent, f"job {index}", minutes=index)
    brief = data(await call(agent, token, "prepare_triage", {"limit": 2}))
    assert (len(brief["jobs"]), brief["pending"]) == (2, 3)


async def test_the_default_batch_is_five_jobs(agent: Agent) -> None:
    token = await taras(agent)
    for index in range(7):
        await seed(agent, f"job {index}", minutes=index)
    brief = data(await call(agent, token, "prepare_triage"))
    assert (len(brief["jobs"]), brief["pending"]) == (5, 7)


async def test_a_posting_with_requirement_sections_comes_with_only_those(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await seed(
        agent,
        "About us\nGreat company.\n\nRequirements:\n- Python\n- Docker\n\n"
        "Benefits:\nFree lunch",
    )
    [job] = data(await call(agent, token, "prepare_triage"))["jobs"]
    assert (job["untrusted_job_text"], job["text_scope"]) == (
        "Requirements:\n- Python\n- Docker",
        "requirements",
    )


async def test_without_the_context_the_brief_has_only_the_jobs(agent: Agent) -> None:
    token = await taras(agent)
    await update_profile(agent, token, FULL)
    number = await seed(agent)
    brief = data(await call(agent, token, "prepare_triage", {"include_context": False}))
    assert [job["job_id"] for job in brief["jobs"]] == [number]
    assert (brief["profile"], brief["rules"], brief["facts"]) == (None, None, None)


async def test_the_context_comes_back_when_asked_for_again(agent: Agent) -> None:
    token = await taras(agent)
    await seed(agent)
    brief = data(await call(agent, token, "prepare_triage", {"include_context": True}))
    assert brief["profile"] is not None
    assert (brief["rules"], brief["facts"]) == (
        (TOOLS.parent.parent / "triage" / "rules.md").read_text(encoding="utf-8"),
        [],
    )


async def test_a_job_the_cron_rated_maybe_is_in_the_brief_but_analyse_is_not(
    agent: Agent,
) -> None:
    token = await taras(agent)
    unsure = await seed(agent, "unsure", minutes=0)
    settled = await seed(agent, "settled", minutes=1)
    await rate_by_rules(agent, unsure, TriageVerdict.MAYBE)
    await rate_by_rules(agent, settled, TriageVerdict.ANALYSE)
    brief = data(await call(agent, token, "prepare_triage"))
    assert ([job["job_id"] for job in brief["jobs"]], brief["pending"]) == (
        [unsure],
        1,
    )


@pytest.mark.parametrize("limit", [0, 6, 20])
async def test_a_limit_outside_the_batch_is_a_tool_error(
    agent: Agent, limit: int
) -> None:
    result = await call(agent, await taras(agent), "prepare_triage", {"limit": limit})
    assert result.is_error is True


async def test_saving_returns_the_ids_per_verdict_and_the_list_shows_the_triage(
    agent: Agent,
) -> None:
    token = await taras(agent)
    a = await seed(agent, "job 0", minutes=0)
    b = await seed(agent, "job 1", minutes=1)
    c = await seed(agent, "job 2", minutes=2)

    saved = data(
        await call(
            agent,
            token,
            "save_triage",
            {
                "items": [
                    item(a, 90, "analyse", "Strong fit"),
                    item(b, 50, "maybe", "Short"),
                    item(c, 5, "skip", "Onsite Berlin"),
                ]
            },
        )
    )

    assert saved["analyse"] == [a]
    assert saved["maybe"] == [b]
    assert saved["skip"] == [c]
    assert saved["saved"] == [
        item(a, 90, "analyse", "Strong fit"),
        item(b, 50, "maybe", "Short"),
        item(c, 5, "skip", "Onsite Berlin"),
    ]
    jobs = data(await call(agent, token, "list_jobs"))["jobs"]
    assert [(j["job_id"], j["triage_score"], j["triage_verdict"]) for j in jobs] == [
        (a, 90, "analyse"),
        (b, 50, "maybe"),
        (c, 5, "skip"),
    ]
    brief = data(await call(agent, token, "prepare_triage"))
    assert (brief["jobs"], brief["pending"]) == ([], 0)


async def test_a_skipped_job_stays_in_the_list_and_the_verdict_filter_works(
    agent: Agent,
) -> None:
    token = await taras(agent)
    a = await seed(agent, "one", minutes=0)
    b = await seed(agent, "two", minutes=1)
    await call(
        agent,
        token,
        "save_triage",
        {"items": [item(a, 1, "skip", "No"), item(b, 99, "analyse", "Yes")]},
    )
    assert await listed(agent, token) == [b, a]
    assert await listed(agent, token, filters={"triage_verdict": "skip"}) == [a]


async def test_a_repeated_triage_overwrites_the_previous_one(agent: Agent) -> None:
    token = await taras(agent)
    a = await seed(agent)
    await call(agent, token, "save_triage", {"items": [item(a, 10, "skip", "No")]})
    await call(agent, token, "save_triage", {"items": [item(a, 80, "analyse", "Yes")]})
    [job] = data(await call(agent, token, "list_jobs"))["jobs"]
    assert (job["triage_score"], job["triage_verdict"]) == (80, "analyse")


async def test_a_bad_item_is_a_tool_error_that_names_it_and_saves_nothing(
    agent: Agent,
) -> None:
    token = await taras(agent)
    a = await seed(agent, "one", minutes=0)
    b = await seed(agent, "two", minutes=1)
    result = await call(
        agent,
        token,
        "save_triage",
        {"items": [item(a), item(b, 101)]},
    )
    assert f"Елемент 2 (вакансія {b}): скор — ціле число від 0 до 100." in error_text(
        result
    )
    assert data(await call(agent, token, "prepare_triage"))["pending"] == 2


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ([], "Порожня пачка: потрібен хоч один елемент."),
        ([item(99)], "Елемент 1: вакансію 99 не знайдено."),
    ],
)
async def test_batch_errors_have_the_v1_text(
    agent: Agent, items: list[dict[str, Any]], message: str
) -> None:
    result = await call(agent, await taras(agent), "save_triage", {"items": items})
    assert message in error_text(result)


async def test_a_job_without_text_cannot_be_triaged(agent: Agent) -> None:
    waiting = await seed(
        agent,
        None,
        url="https://www.linkedin.com/jobs/view/4012345678",
        linkedin_id="4012345678",
        source="linkedin_alert",
    )
    result = await call(
        agent, await taras(agent), "save_triage", {"items": [item(waiting)]}
    )
    assert f"Елемент 1: у вакансії {waiting} нема тексту опису." in error_text(result)


async def test_a_batch_over_five_is_rejected_by_the_schema(agent: Agent) -> None:
    token = await taras(agent)
    numbers = [await seed(agent, f"job {index}", minutes=index) for index in range(6)]
    result = await call(
        agent, token, "save_triage", {"items": [item(number) for number in numbers]}
    )
    assert result.is_error is True
    assert (
        data(await call(agent, token, "prepare_triage", {"limit": 5}))["pending"] == 6
    )


async def test_a_user_does_not_see_or_triage_the_jobs_of_another(agent: Agent) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    mine = await seed(agent)
    await call(
        agent, taras_token, "save_triage", {"items": [item(mine, 90, "analyse")]}
    )

    assert data(await call(agent, katya_token, "prepare_triage"))["pending"] == 0
    stolen = await call(agent, katya_token, "save_triage", {"items": [item(mine)]})
    assert f"Елемент 1: вакансію {mine} не знайдено." in error_text(stolen)
    [theirs] = [await seed(agent, who="katya@example.com")]
    [job] = data(await call(agent, katya_token, "list_jobs"))["jobs"]
    assert (job["job_id"], job["triage_verdict"]) == (theirs, None)


@pytest.mark.parametrize(
    "status", [ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN]
)
async def test_a_job_with_a_closed_application_leaves_the_brief(
    agent: Agent, status: ApplicationStatus
) -> None:
    closed = await seed(agent, "closed")
    kept = await seed(agent, "kept", minutes=1)
    await close_application(agent, closed, status)
    brief = data(await call(agent, await taras(agent), "prepare_triage", {}))
    assert ([job["job_id"] for job in brief["jobs"]], brief["pending"]) == ([kept], 1)


@pytest.mark.parametrize(
    "status", [ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN]
)
async def test_a_job_with_a_closed_application_cannot_be_triaged(
    agent: Agent, status: ApplicationStatus
) -> None:
    fine = await seed(agent, "fine")
    closed = await seed(agent, "closed", minutes=1)
    await close_application(agent, closed, status)
    result = await call(
        agent,
        await taras(agent),
        "save_triage",
        {"items": [item(fine), item(closed)]},
    )
    assert (
        f"Елемент 2: вакансію {closed} відхилено або відкликано в подачі."
        in error_text(result)
    )
    assert (
        await listed(agent, await taras(agent), filters={"triage_verdict": "maybe"})
        == []
    )
