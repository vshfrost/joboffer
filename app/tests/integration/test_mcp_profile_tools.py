"""Тули профілю через SDK-клієнт: DCR → токен → `tools/list` і виклики на справжньому Postgres."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.identity import CreateUser
from bootstrap.agent import create_agent_app
from bootstrap.container import Container
from bootstrap.settings import Settings
from tests.integration.test_agent_http import (
    BASE,
    OTHER_PASSWORD,
    PASSWORD,
    PUBLIC,
    Agent,
    tokens_for,
)

pytestmark = pytest.mark.anyio

TOOLS = Path(__file__).resolve().parents[2] / "prompts" / "mcp" / "tools"

EMPTY: dict[str, Any] = {
    "roles": [],
    "work_modes": [],
    "locations": [],
    "include_unknown_mode": True,
    "relocation": False,
    "target_domains": [],
    "seniority": [],
    "min_salary_eur": None,
    "stop_words": [],
    "title_keywords": [],
    "title_exclude": [],
    "full_name": "",
    "email": "",
    "phone": "",
    "linkedin_url": "",
    "city": "",
    "github_url": "",
    "work_authorization": "",
}
FULL: dict[str, Any] = {
    "roles": ["Backend Engineer", "SRE"],
    "work_modes": ["remote", "hybrid"],
    "locations": [
        {"place": "Valencia", "aliases": ["Валенсія"], "work_modes": ["hybrid"]},
        {"place": "Madrid", "aliases": [], "work_modes": ["remote", "onsite"]},
    ],
    "include_unknown_mode": False,
    "relocation": True,
    "target_domains": ["fintech", "payments"],
    "seniority": ["senior", "lead"],
    "min_salary_eur": 70000,
    "stop_words": ["crypto"],
    "title_keywords": ["backend"],
    "title_exclude": ["junior", "intern"],
    "full_name": "Test User",
    "email": "user@example.com",
    "phone": "+34 600 000 000",
    "linkedin_url": "https://linkedin.com/in/user",
    "city": "Valencia, Spain",
    "github_url": "https://github.com/user",
    "work_authorization": "Spain / EU work authorization",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def agent(
    portal: BlockingPortal, engine: AsyncEngine, database_url: str
) -> AsyncIterator[Agent]:
    """Агент зі стандартним набором тулів (без `tools=`): так він і запускається."""

    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
            await conn.execute(text("TRUNCATE oauth_clients CASCADE"))
            await conn.execute(text("TRUNCATE login_failures"))

    portal.call(clean)
    app = create_agent_app(
        Settings(environment="test", database_url=database_url, web_public_url=BASE)
    )
    container: Container = app.state.container
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1:8798"
        ) as http,
    ):
        user_ids = {}
        for email, password in (
            ("taras@example.com", PASSWORD),
            ("katya@example.com", OTHER_PASSWORD),
        ):
            created = await container.identity.create_user(
                CreateUser(email=email, display_name="Користувач", password=password)
            )
            user_ids[email] = created.id
        yield Agent(app, http, container, user_ids)


async def call(
    agent: Agent, token: str, name: str, arguments: dict[str, Any] | None = None
) -> CallToolResult:
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            return await client.call_tool(name, arguments or {})


async def get_profile(agent: Agent, token: str) -> dict[str, Any]:
    result = await call(agent, token, "get_profile")
    assert result.is_error is False
    assert result.structured_content is not None
    return dict(result.structured_content)


async def update_profile(
    agent: Agent, token: str, profile: dict[str, Any]
) -> CallToolResult:
    return await call(agent, token, "update_profile", {"profile": profile})


async def taras(agent: Agent) -> str:
    return (await tokens_for(agent))["access_token"]


async def katya(agent: Agent) -> str:
    issued = await tokens_for(agent, "katya@example.com", OTHER_PASSWORD)
    return issued["access_token"]


async def test_tools_list_has_both_profile_tools_with_the_catalog_descriptions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert {"get_profile", "update_profile"} <= set(tools)
    for name in ("get_profile", "update_profile"):
        assert tools[name].description == (TOOLS / f"{name}.md").read_text(
            encoding="utf-8"
        )


async def test_a_new_user_gets_an_empty_profile(agent: Agent) -> None:
    assert await get_profile(agent, await taras(agent)) == EMPTY


async def test_update_then_get_returns_the_same_profile(agent: Agent) -> None:
    token = await taras(agent)
    updated = await update_profile(agent, token, FULL)

    assert updated.is_error is False
    assert updated.structured_content == FULL
    assert await get_profile(agent, token) == FULL


async def test_update_replaces_the_whole_profile(agent: Agent) -> None:
    token = await taras(agent)
    await update_profile(agent, token, FULL)

    await update_profile(agent, token, {"roles": ["QA"]})

    assert await get_profile(agent, token) == {**EMPTY, "roles": ["QA"]}


async def test_values_are_normalized_like_in_the_web_profile(agent: Agent) -> None:
    token = await taras(agent)
    await update_profile(
        agent,
        token,
        {
            "roles": ["  SRE ", "sre"],
            "seniority": ["lead", "junior"],
            "city": " Valencia,  Spain ",
        },
    )

    saved = await get_profile(agent, token)

    assert saved["roles"] == ["SRE"]
    assert saved["seniority"] == ["junior", "lead"]
    assert saved["city"] == "Valencia, Spain"


@pytest.mark.parametrize(
    ("profile", "message"),
    [
        ({"min_salary_eur": -1}, "Мінімальна зарплата не може бути від'ємною."),
        (
            {
                "locations": [
                    {"place": "Valencia", "aliases": [], "work_modes": ["remote"]},
                    {"place": "VALENCIA", "aliases": [], "work_modes": ["remote"]},
                ]
            },
            "Місця в локаціях пошуку не мають повторюватись.",
        ),
        (
            {"email": "not-an-email"},
            "Email виглядає некоректно, напр. name@example.com.",
        ),
        ({"linkedin_url": "linkedin.com/in/user"}, "LinkedIn — посилання з https://."),
    ],
)
async def test_invalid_data_is_a_tool_error_with_the_domain_text_and_changes_nothing(
    agent: Agent, profile: dict[str, Any], message: str
) -> None:
    token = await taras(agent)
    await update_profile(agent, token, FULL)

    result = await update_profile(agent, token, profile)

    assert result.is_error is True
    assert message in result.content[0].text  # type: ignore[union-attr]
    assert await get_profile(agent, token) == FULL


@pytest.mark.parametrize(
    "profile",
    [
        {"seniority": ["wizard"]},
        {"work_modes": ["office"]},
        {"locations": [{"place": "Valencia", "aliases": [], "work_modes": []}]},
        {"locations": [{"aliases": [], "work_modes": ["remote"]}]},
    ],
)
async def test_data_outside_the_schema_is_a_tool_error(
    agent: Agent, profile: dict[str, Any]
) -> None:
    token = await taras(agent)
    await update_profile(agent, token, FULL)

    result = await update_profile(agent, token, profile)

    assert result.is_error is True
    assert await get_profile(agent, token) == FULL


async def test_a_user_does_not_see_another_users_profile(agent: Agent) -> None:
    await update_profile(agent, await taras(agent), FULL)

    assert await get_profile(agent, await katya(agent)) == EMPTY


async def test_a_user_cannot_change_another_users_profile(agent: Agent) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    await update_profile(agent, taras_token, FULL)

    await update_profile(agent, katya_token, {"roles": ["Designer"]})

    assert await get_profile(agent, taras_token) == FULL
    assert (await get_profile(agent, katya_token))["roles"] == ["Designer"]
