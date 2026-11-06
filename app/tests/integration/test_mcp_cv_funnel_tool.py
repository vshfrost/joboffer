"""`get_cv_funnel` через SDK-клієнт на справжньому Postgres: звіт за версіями CV, «unknown» для подачі
без CV, ізоляція користувачів."""

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from tests.integration.test_agent_http import PUBLIC, Agent
from tests.integration.test_mcp_application_tools import mark, move
from tests.integration.test_mcp_job_tools import add, data
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


async def test_the_tool_description_is_the_catalog_text(agent: Agent) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert tools["get_cv_funnel"].description == (TOOLS / "get_cv_funnel.md").read_text(
        encoding="utf-8"
    )


async def test_an_application_without_a_cv_is_counted_under_unknown(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await add(agent, token)
    await mark(agent, token)
    await move(agent, token, "interview")

    report = data(await call(agent, token, "get_cv_funnel"))

    assert report["versions"] == [
        {
            "cv_number": "unknown",
            "cv_date": None,
            "coverage_percent": None,
            "applications": 1,
            "replies": 1,
            "interviews": 1,
        }
    ]


async def test_another_user_does_not_see_the_applications_in_the_report(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await add(agent, token)
    await mark(agent, token)

    report = data(await call(agent, await katya(agent), "get_cv_funnel"))

    assert report["versions"] == []
