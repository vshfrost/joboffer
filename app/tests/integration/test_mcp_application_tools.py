"""Тули подач через SDK-клієнт: DCR → токен → `tools/list` і виклики на справжньому Postgres."""

from typing import Any

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

from tests.integration.test_agent_http import PUBLIC, Agent
from tests.integration.test_mcp_job_tools import (
    add,
    data,
    error_text,
    listed,
)
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

APPLICATION_TOOLS = {"mark_applied", "set_application_status"}


async def mark(
    agent: Agent, token: str, job_id: int = 1, **application: Any
) -> CallToolResult:
    arguments = {"job_id": job_id, "application": {"channel": "email"} | application}
    return await call(agent, token, "mark_applied", arguments)


async def move(
    agent: Agent, token: str, status: str, job_id: int = 1
) -> CallToolResult:
    arguments = {"job_id": job_id, "status": status}
    return await call(agent, token, "set_application_status", arguments)


async def test_tools_list_has_both_application_tools_with_the_catalog_descriptions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools) >= APPLICATION_TOOLS
    for name in APPLICATION_TOOLS:
        assert tools[name].description == (TOOLS / f"{name}.md").read_text(
            encoding="utf-8"
        )


async def test_marking_a_job_applied_returns_the_v1_view(agent: Agent) -> None:
    token = await taras(agent)
    await add(agent, token)
    view = data(
        await mark(
            agent,
            token,
            channel="ats",
            applied_on="2026-01-01",
            ats="greenhouse",
            company_domains=["https://www.Acme.com/jobs"],
            company_emails=["HR@Acme.com"],
        )
    )
    changed = view.pop("status_changed")
    assert len(changed) == 10
    assert view == {
        "job_id": 1,
        "status": "applied",
        "applied_on": "2026-01-01",
        "channel": "ats",
        "ats": "greenhouse",
        "company_domains": ["acme.com"],
        "company_emails": ["hr@acme.com"],
    }


async def test_the_default_date_is_a_day_not_in_the_future(agent: Agent) -> None:
    token = await taras(agent)
    await add(agent, token)
    view = data(await mark(agent, token))
    assert len(view["applied_on"]) == 10
    assert view["applied_on"] <= view["status_changed"]


async def test_marking_again_replaces_the_details_and_keeps_the_status(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await add(agent, token)
    await mark(agent, token, company_emails=["a@acme.com"])
    await move(agent, token, "interview")
    again = data(await mark(agent, token, channel="referral", ats="lever"))
    assert (again["status"], again["channel"], again["ats"]) == (
        "interview",
        "referral",
        "lever",
    )
    assert again["company_emails"] == []


async def test_an_unknown_job_is_a_tool_error(agent: Agent) -> None:
    token = await taras(agent)
    assert "Вакансію 9 не знайдено." in error_text(await mark(agent, token, job_id=9))


async def test_invalid_details_are_a_tool_error_with_the_v1_text(agent: Agent) -> None:
    token = await taras(agent)
    await add(agent, token)
    result = await mark(agent, token, applied_on="02.03.2026")
    assert "Дата подачі — у форматі YYYY-MM-DD." in error_text(result)
    result = await mark(agent, token, company_domains=["no"])
    assert "Некоректний домен компанії: no." in error_text(result)
    assert (
        data(await call(agent, token, "get_job", {"job_id": 1}))["application"] is None
    )


async def test_an_unknown_channel_is_refused_by_the_schema(agent: Agent) -> None:
    token = await taras(agent)
    await add(agent, token)
    assert (await mark(agent, token, channel="phone")).is_error is True


async def test_moving_the_application_forward_returns_the_new_status(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await add(agent, token)
    await mark(agent, token)
    assert data(await move(agent, token, "replied"))["status"] == "replied"
    assert data(await move(agent, token, "offer"))["status"] == "offer"


async def test_the_same_status_changes_nothing(agent: Agent) -> None:
    token = await taras(agent)
    await add(agent, token)
    first = data(await mark(agent, token))
    assert data(await move(agent, token, "applied")) == first


async def test_a_closed_application_and_a_move_back_are_tool_errors(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await add(agent, token)
    await mark(agent, token)
    await move(agent, token, "interview")
    assert "Статус interview → applied неможливий" in error_text(
        await move(agent, token, "applied")
    )
    await move(agent, token, "rejected")
    assert "Подачу вже закрито (rejected): статус більше не змінюється." in error_text(
        await move(agent, token, "offer")
    )


async def test_moving_a_job_without_application_says_to_mark_it_first(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await add(agent, token)
    assert "Подачі на вакансію 1 нема: спершу mark_applied." in error_text(
        await move(agent, token, "replied")
    )


async def test_get_job_returns_the_application(agent: Agent) -> None:
    token = await taras(agent)
    await add(agent, token)
    await mark(agent, token, channel="linkedin", applied_on="2026-01-01")
    await move(agent, token, "replied")
    job = data(await call(agent, token, "get_job", {"job_id": 1}))
    application = job["application"]
    assert len(application.pop("status_changed")) == 10
    assert application == {
        "job_id": 1,
        "status": "replied",
        "applied_on": "2026-01-01",
        "channel": "linkedin",
        "ats": None,
        "company_domains": [],
        "company_emails": [],
    }


async def test_the_list_shows_the_status_and_filters_by_it(agent: Agent) -> None:
    token = await taras(agent)
    await add(agent, token, text="one")
    await add(agent, token, text="two")
    await add(agent, token, text="three")
    await mark(agent, token, job_id=2)
    await mark(agent, token, job_id=3)
    await move(agent, token, "offer", job_id=3)
    rows = {
        item["job_id"]: item["status"]
        for item in data(await call(agent, token, "list_jobs"))["jobs"]
    }
    assert rows == {1: None, 2: "applied", 3: "offer"}
    assert await listed(agent, token, filters={"status": "offer"}) == [3]
    assert await listed(agent, token, filters={"status": "applied"}) == [2]
    assert await listed(agent, token, filters={"status": "rejected"}) == []


async def test_a_rejected_job_stays_in_the_agent_list_and_its_status_filter(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await add(agent, token, text="rejected one")
    await add(agent, token, text="plain one")
    await mark(agent, token, job_id=1)
    await move(agent, token, "rejected", job_id=1)
    rows = {
        item["job_id"]: item["status"]
        for item in data(await call(agent, token, "list_jobs"))["jobs"]
    }
    assert rows == {1: "rejected", 2: None}
    assert await listed(agent, token, filters={"status": "rejected"}) == [1]


async def test_an_unknown_status_filter_is_refused_by_the_schema(agent: Agent) -> None:
    token = await taras(agent)
    result = await call(agent, token, "list_jobs", {"filters": {"status": "active"}})
    assert result.is_error is True


async def test_an_applied_job_cannot_be_dismissed(agent: Agent) -> None:
    token = await taras(agent)
    await add(agent, token, text="keep")
    await add(agent, token, text="second")
    await mark(agent, token, job_id=2)
    result = await call(
        agent, token, "dismiss_jobs", {"job_ids": [1, 2], "reason": "не цікаво"}
    )
    assert "Елемент 2: на вакансію 2 уже є подача — поданих вакансій не ховають." in (
        error_text(result)
    )
    assert await listed(agent, token) == [2, 1]


async def test_a_user_does_not_see_or_change_the_application_of_another(
    agent: Agent,
) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    await add(agent, taras_token)
    await add(agent, katya_token)
    await mark(agent, taras_token)
    assert (
        data(await call(agent, katya_token, "get_job", {"job_id": 1}))["application"]
        is None
    )
    assert "Подачі на вакансію 1 нема" in error_text(
        await move(agent, katya_token, "offer")
    )
    assert await listed(agent, katya_token, filters={"status": "applied"}) == []
    assert await listed(agent, taras_token, filters={"status": "applied"}) == [1]
