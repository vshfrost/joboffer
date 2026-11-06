"""Тули вакансій через SDK-клієнт: DCR → токен → `tools/list` і виклики на справжньому Postgres."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from tests.integration.test_agent_http import PUBLIC, Agent
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

JOB_TOOLS = {"add_job", "get_job", "list_jobs", "dismiss_jobs", "restore_job"}
POSTING = "Senior Python engineer. Remote. Asyncio, Postgres."
ALERT_LINK = (
    "https://es.linkedin.com/comm/jobs/view/dev-at-acme-4012345678/?trackingId=x"
)


def data(result: CallToolResult) -> dict[str, Any]:
    assert result.is_error is False, result.content
    assert result.structured_content is not None
    return dict(result.structured_content)


def error_text(result: CallToolResult) -> str:
    assert result.is_error is True
    return result.content[0].text  # type: ignore[union-attr]


async def add(agent: Agent, token: str, **fields: str) -> CallToolResult:
    return await call(agent, token, "add_job", {"text": POSTING} | fields)


async def listed(agent: Agent, token: str, **arguments: Any) -> list[int]:
    result = await call(agent, token, "list_jobs", arguments)
    return [item["job_id"] for item in data(result)["jobs"]]


async def test_tools_list_has_the_five_job_tools_with_the_catalog_descriptions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools) >= JOB_TOOLS
    for name in JOB_TOOLS:
        assert tools[name].description == (TOOLS / f"{name}.md").read_text(
            encoding="utf-8"
        )


async def test_initialize_returns_the_new_instructions_file(agent: Agent) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            instructions = client.instructions

    expected = (TOOLS.parent / "instructions.md").read_text(encoding="utf-8")
    assert instructions == expected
    assert "dismiss_jobs" in expected
    assert "filtered_out" in expected


async def test_add_then_get_returns_the_same_job(agent: Agent) -> None:
    token = await taras(agent)
    added = data(
        await add(
            agent,
            token,
            url="https://Acme.com/jobs/1/?utm_source=x",
            title="Backend",
            company="Acme",
        )
    )
    assert added == {"job_id": 1, "duplicate": False}

    job = data(await call(agent, token, "get_job", {"job_id": 1}))
    added_on = job.pop("added")
    assert len(added_on) == 10
    assert job == {
        "job_id": 1,
        "title": "Backend",
        "company": "Acme",
        "url": "https://acme.com/jobs/1",
        "source": "manual",
        "needs_text": False,
        "untrusted_job_text": POSTING,
        "dismissed": False,
        "dismiss_reason": None,
        "application": None,
    }


async def test_adding_the_same_posting_again_is_a_duplicate(agent: Agent) -> None:
    token = await taras(agent)
    await add(agent, token)
    again = data(await add(agent, token, text=f"  {POSTING.upper()}  "))
    assert again == {"job_id": 1, "duplicate": True}
    same_url = data(
        await call(agent, token, "add_job", {"text": "other", "url": "https://x.com/a"})
    )
    repeat = data(
        await call(
            agent, token, "add_job", {"text": "x", "url": "https://X.com/a/#top"}
        )
    )
    assert repeat == {"job_id": same_url["job_id"], "duplicate": True}


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"text": ""}, "Встав текст опису вакансії."),
        ({"text": "x" * 100_001}, "Опис задовгий: більше 100000 символів."),
        (
            {"text": "x", "url": "example.com/a"},
            "Посилання має починатися з http:// або https://.",
        ),
    ],
)
async def test_an_invalid_job_is_a_tool_error_with_the_v1_text(
    agent: Agent, arguments: dict[str, str], message: str
) -> None:
    token = await taras(agent)
    result = await call(agent, token, "add_job", arguments)
    assert message in error_text(result)
    assert await listed(agent, token) == []


async def test_a_missing_job_is_a_tool_error(agent: Agent) -> None:
    result = await call(agent, await taras(agent), "get_job", {"job_id": 7})
    assert "Вакансію 7 не знайдено." in error_text(result)


async def test_the_list_has_the_summary_fields_and_no_text(agent: Agent) -> None:
    token = await taras(agent)
    await add(agent, token, title="Backend", company="Acme")
    item = data(await call(agent, token, "list_jobs"))["jobs"][0]
    item.pop("added")
    assert item == {
        "job_id": 1,
        "title": "Backend",
        "company": "Acme",
        "url": None,
        "source": "manual",
        "needs_text": False,
        "dismissed": False,
        "score": None,
        "filters_passed": None,
        "work_mode": None,
        "status": None,
        "triage_score": None,
        "triage_verdict": None,
    }


async def test_the_list_filters_and_limit(agent: Agent) -> None:
    token = await taras(agent)
    await add(agent, token, text="we like Rust", title="Engineer")
    await add(agent, token, text="python only", title="Dev", company="Acme")
    assert await listed(agent, token, filters={"query": "rust"}) == [1]
    assert await listed(agent, token, filters={"query": "acme"}) == [2]
    assert await listed(agent, token, filters={"source": "manual", "days": 7}) == [2, 1]
    assert await listed(agent, token, filters={"source": "other"}) == []
    assert await listed(agent, token, limit=1) == [2]
    assert await listed(agent, token, filters={"needs_text": True}) == []


async def test_invalid_filters_are_a_tool_error(agent: Agent) -> None:
    token = await taras(agent)
    result = await call(agent, token, "list_jobs", {"filters": {"days": 0}})
    assert "Свіжість — ціле число днів від 1 до 3650." in error_text(result)
    assert (await call(agent, token, "list_jobs", {"limit": 0})).is_error is True
    assert (await call(agent, token, "list_jobs", {"limit": 201})).is_error is True


async def test_dismissed_jobs_leave_the_list_and_show_with_the_flag(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await add(agent, token, text="keep")
    await add(agent, token, text="gone")
    result = data(
        await call(
            agent, token, "dismiss_jobs", {"job_ids": [2], "reason": "не цікаво"}
        )
    )
    assert result == {"dismissed": [2]}
    assert await listed(agent, token) == [1]
    assert await listed(agent, token, filters={"dismissed": True}) == [2]
    hidden = data(await call(agent, token, "get_job", {"job_id": 2}))
    assert (hidden["dismissed"], hidden["dismiss_reason"]) == (True, "не цікаво")


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"job_ids": [], "reason": "x"}, "Порожня пачка: потрібна хоч одна вакансія."),
        ({"job_ids": [1, 99], "reason": "x"}, "Елемент 2: вакансію 99 не знайдено."),
        (
            {"job_ids": [1, 1], "reason": "x"},
            "Елемент 2: вакансія 1 уже є в елементі 1.",
        ),
        ({"job_ids": [99], "reason": "x"}, "Вакансію 99 не знайдено."),
        ({"job_ids": [1], "reason": "  "}, "Вкажи причину приховування."),
    ],
)
async def test_a_failed_batch_is_a_tool_error_with_the_item_number_and_hides_nothing(
    agent: Agent, arguments: dict[str, Any], message: str
) -> None:
    token = await taras(agent)
    await add(agent, token)
    assert message in error_text(await call(agent, token, "dismiss_jobs", arguments))
    assert await listed(agent, token) == [1]


async def test_a_batch_over_fifty_or_a_long_reason_is_a_tool_error(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await add(agent, token)
    too_many = {"job_ids": list(range(1, 52)), "reason": "x"}
    assert (await call(agent, token, "dismiss_jobs", too_many)).is_error is True
    long_reason = {"job_ids": [1], "reason": "x" * 201}
    assert (await call(agent, token, "dismiss_jobs", long_reason)).is_error is True
    assert await listed(agent, token) == [1]


async def test_restore_brings_the_job_back_and_leaves_a_visible_one_alone(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await add(agent, token, text="one")
    await add(agent, token, text="two")
    await call(agent, token, "dismiss_jobs", {"job_ids": [1], "reason": "x"})
    assert data(await call(agent, token, "restore_job", {"job_id": 1})) == {"job_id": 1}
    assert data(await call(agent, token, "restore_job", {"job_id": 2})) == {"job_id": 2}
    assert await listed(agent, token) == [2, 1]


async def test_restoring_a_missing_job_is_a_tool_error(agent: Agent) -> None:
    result = await call(agent, await taras(agent), "restore_job", {"job_id": 5})
    assert "Вакансію 5 не знайдено." in error_text(result)


async def test_a_user_does_not_see_or_change_another_users_jobs(agent: Agent) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    await add(agent, taras_token)

    assert await listed(agent, katya_token) == []
    missing = await call(agent, katya_token, "get_job", {"job_id": 1})
    assert "Вакансію 1 не знайдено." in error_text(missing)
    dismiss = await call(
        agent, katya_token, "dismiss_jobs", {"job_ids": [1], "reason": "x"}
    )
    assert dismiss.is_error is True
    assert (await call(agent, katya_token, "restore_job", {"job_id": 1})).is_error
    assert await listed(agent, taras_token) == [1]
    # Той самий текст в іншого користувача — нова вакансія з його номером 1.
    assert data(await add(agent, katya_token)) == {"job_id": 1, "duplicate": False}


async def seed_waiting_job(agent: Agent) -> int:
    """Вакансія з листа-алерту LinkedIn (її створить B10): без тексту, є посилання, посада й компанія."""
    async with agent.container.unit_of_work() as tx:
        number = await tx.jobs.add(
            UserId.parse(agent.user_ids["taras@example.com"]),
            JobId(uuid4()),
            NewJob(
                text=None,
                url="https://www.linkedin.com/jobs/view/4012345678",
                title="Backend Dev",
                company="Acme",
                linkedin_id="4012345678",
                source="linkedin_alert",
            ),
            datetime.now(UTC),
        )
        await tx.commit()
        return number


async def test_a_linkedin_link_adds_the_text_to_the_waiting_job(agent: Agent) -> None:
    token = await taras(agent)
    waiting = await seed_waiting_job(agent)
    before = data(await call(agent, token, "get_job", {"job_id": waiting}))
    assert (before["needs_text"], before["untrusted_job_text"]) == (True, None)
    assert await listed(agent, token, filters={"needs_text": True}) == [waiting]

    added = data(
        await add(agent, token, url=ALERT_LINK, title="Other", company="Other")
    )

    assert added == {"job_id": waiting, "duplicate": False}
    after = data(await call(agent, token, "get_job", {"job_id": waiting}))
    assert (after["needs_text"], after["untrusted_job_text"]) == (False, POSTING)
    assert (after["title"], after["company"]) == ("Backend Dev", "Acme")
    assert await listed(agent, token, filters={"needs_text": True}) == []
    again = data(await add(agent, token, text="Another text", url=ALERT_LINK))
    assert again == {"job_id": waiting, "duplicate": True}
