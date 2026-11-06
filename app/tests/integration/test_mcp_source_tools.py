"""Тули `get_sources` і `refresh_sources` через SDK-клієнт: DCR → токен → виклик на справжньому Postgres.

Компанії й стрічки, стан їх прогонів, ліміт «оновити зараз» (помилка тулу з часом за Мадридом) і
вакансії, що вже не проходять фільтр профілю, — окремо для кожного користувача."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import text

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.sources import FeedInput
from application.sources.refresh import SourceRunUseCases
from domain.identity.ids import UserId
from domain.shared.local_time import local_time
from domain.sources.kinds import FeedSource, Platform
from domain.sources.posting import Posting
from infrastructure.system import RandomIds
from tests.integration.test_agent_http import BASE, PUBLIC, Agent
from tests.integration.test_mcp_job_tools import data, error_text
from tests.integration.test_mcp_mail_tools import agent
from tests.integration.test_mcp_profile_tools import (
    FULL,
    TOOLS,
    anyio_backend,
    call,
    katya,
    taras,
    update_profile,
)
from tests.support.clock import FakeClock
from tests.support.source_runs import registry

__all__ = ["agent", "anyio_backend"]

pytestmark = pytest.mark.anyio

QUEUED = "Refresh requested: the server starts it within about a minute."
COMPANY_ID = UUID("5f1b7d0e-2f3a-4b6c-9d1e-0a1b2c3d4e5f")
LIMIT = "Оновлення джерел уже запитано 2 рази за 30 хв — наступне о "


def actor_of(agent: Agent, email: str = "taras@example.com") -> Actor:
    return Actor(
        user_id=UserId(UUID(agent.user_ids[email])),
        channel=Channel.WEB,
        client_id="web",
        grant_id=None,
        scopes=frozenset(Scope),
        correlation_id="test",
    )


async def sources(agent: Agent, token: str) -> dict[str, Any]:
    return data(await call(agent, token, "get_sources"))


async def seed_sources(agent: Agent, *titles: str) -> None:
    """Компанія й стрічка користувача; справжній прогін на тій самій базі, час стоїть на 2026-01-01 09:00 UTC."""
    me = actor_of(agent)
    await agent.container.sources.add_feed(me, FeedInput("dou", "category=Python"))
    async with agent.container.engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO source_companies (id, user_id, platform, slug, name) "
                "VALUES (:id, :user, 'greenhouse', 'acme', 'Acme')"
            ),
            {"id": COMPANY_ID, "user": UUID(agent.user_ids["taras@example.com"])},
        )
    scripts = registry([*Platform, *FeedSource], [])
    scripts[Platform.GREENHOUSE].postings["acme"] = [
        Posting(
            title=title,
            url=f"https://jobs.example/{n}",
            text=f"Опис вакансії «{title}»",
        )
        for n, title in enumerate(titles, start=1)
    ]
    runs = SourceRunUseCases(
        agent.container.unit_of_work,
        scripts,
        FakeClock(datetime(2026, 1, 1, 9, 0, tzinfo=UTC)),
        RandomIds(),
    )
    await runs.refresh_sources()


async def test_tools_list_has_both_source_tools_with_the_catalog_descriptions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert {"get_sources", "refresh_sources"} <= set(tools)
    for name in ("get_sources", "refresh_sources"):
        assert tools[name].description == (TOOLS / f"{name}.md").read_text(
            encoding="utf-8"
        )


async def test_a_new_user_has_no_sources_two_requests_and_a_settings_link(
    agent: Agent,
) -> None:
    view = await sources(agent, await taras(agent))

    assert view == {
        "companies": [],
        "feeds": [],
        "refresh_requests_left": 2,
        "next_refresh_at": None,
        "filtered_out": {"count": 0, "jobs": []},
        "settings_url": f"{BASE}/sources",
    }


async def test_sources_show_their_last_run_with_the_madrid_time(agent: Agent) -> None:
    await seed_sources(agent, "Backend Engineer", "Data Engineer")
    token = await taras(agent)

    view = await sources(agent, token)

    run = {
        "ran_at": "2026-01-01 10:00",
        "found": 2,
        "imported": 2,
        "filtered": 0,
        "duplicate": 0,
        "completed": 0,
        "error": None,
    }
    assert view["companies"] == [
        {
            "name": "Acme",
            "platform": "greenhouse",
            "slug": "acme",
            "enabled": True,
            "last_run": run,
        }
    ]
    assert view["feeds"] == [
        {
            "source": "dou",
            "query": "category=Python",
            "enabled": True,
            "last_run": run | {"found": 0, "imported": 0},
        }
    ]


async def test_filtered_out_lists_jobs_the_current_profile_would_not_take(
    agent: Agent,
) -> None:
    await seed_sources(agent, "Backend Engineer", "Product Manager")
    token = await taras(agent)
    assert (await update_profile(agent, token, FULL)).is_error is False

    view = await sources(agent, token)

    jobs = view["filtered_out"]["jobs"]
    assert view["filtered_out"]["count"] == 1
    assert [(j["title"], j["company"], j["reason"]) for j in jobs] == [
        ("Product Manager", "Acme", "title")
    ]
    listed = await call(agent, token, "list_jobs")
    numbers = {j["title"]: j["job_id"] for j in data(listed)["jobs"]}
    assert jobs[0]["job_id"] == numbers["Product Manager"]


async def test_other_users_do_not_see_my_sources_or_filtered_jobs(
    agent: Agent,
) -> None:
    await seed_sources(agent, "Product Manager")
    token = await taras(agent)
    await update_profile(agent, token, FULL)

    theirs = await sources(agent, await katya(agent))

    assert (theirs["companies"], theirs["feeds"]) == ([], [])
    assert theirs["filtered_out"] == {"count": 0, "jobs": []}


async def test_refresh_only_queues_a_request_and_counts_it(agent: Agent) -> None:
    token = await taras(agent)

    first = data(await call(agent, token, "refresh_sources"))

    assert first == {
        "requested": True,
        "refresh_requests_left": 1,
        "message": QUEUED,
    }
    view = await sources(agent, token)
    assert (view["refresh_requests_left"], view["next_refresh_at"]) == (1, None)
    async with agent.container.engine.connect() as conn:
        pending = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM source_refresh_requests WHERE handled_at IS NULL"
                )
            )
        ).scalar_one()
    assert pending == 1


async def test_the_second_request_says_when_the_next_one_is_possible(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await call(agent, token, "refresh_sources")
    await call(agent, token, "refresh_sources")

    view = await sources(agent, token)

    first = await first_request(agent)
    assert view["refresh_requests_left"] == 0
    assert (
        view["next_refresh_at"]
        == f"{local_time(first + timedelta(minutes=30)):%Y-%m-%d %H:%M}"
    )


async def first_request(agent: Agent) -> datetime:
    async with agent.container.engine.connect() as conn:
        found = (
            await conn.execute(
                text("SELECT min(requested_at) FROM source_refresh_requests")
            )
        ).scalar_one()
    assert isinstance(found, datetime)
    return found


async def test_the_third_request_is_a_tool_error_with_the_madrid_time(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await call(agent, token, "refresh_sources")
    await call(agent, token, "refresh_sources")

    third = await call(agent, token, "refresh_sources")

    first = await first_request(agent)
    expected = f"{LIMIT}{local_time(first + timedelta(minutes=30)):%H:%M} (Мадрид)."
    assert expected in error_text(third)
    assert re.fullmatch(r".* \d\d:\d\d \(Мадрид\)\.", expected)


async def test_requests_are_counted_per_user(agent: Agent) -> None:
    mine, theirs = await taras(agent), await katya(agent)
    await call(agent, mine, "refresh_sources")
    await call(agent, mine, "refresh_sources")

    result = await call(agent, theirs, "refresh_sources")

    assert data(result)["refresh_requests_left"] == 1
