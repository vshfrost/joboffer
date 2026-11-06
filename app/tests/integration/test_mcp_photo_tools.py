"""Тул `list_photos` через SDK-клієнт: DCR → токен → `tools/list` і виклики на справжньому Postgres."""

from datetime import UTC, datetime
from typing import Any

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from application.contracts.actor import Actor, Channel, Scope
from domain.identity.ids import UserId
from domain.shared.local_time import local_day
from tests.integration.test_agent_http import BASE, PUBLIC, Agent
from tests.integration.test_mcp_job_tools import data
from tests.integration.test_mcp_profile_tools import (
    TOOLS,
    agent,
    anyio_backend,
    call,
    katya,
    taras,
)
from tests.support.images import FRAME, jpeg

__all__ = ["agent", "anyio_backend"]

pytestmark = pytest.mark.anyio

WEB = BASE  # агент і веб — один origin: адреса агента рахується з web_public_url


@pytest.fixture(autouse=True)
def _web_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBOFFER_WEB_PUBLIC_URL", WEB)


async def add_photo(agent: Agent, email: str, label: str = "") -> None:
    """Фото додає лише веб; тут — через use case, як це робить обробник завантаження."""
    actor = Actor(
        user_id=UserId.parse(agent.user_ids[email]),
        channel=Channel.WEB,
        client_id="web",
        grant_id=None,
        scopes=frozenset(Scope),
        correlation_id="test",
    )
    await agent.container.photos.add_photo(actor, jpeg(*FRAME), label)


async def test_tools_list_has_list_photos_with_the_catalog_description(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert tools["list_photos"].description == (TOOLS / "list_photos.md").read_text(
        encoding="utf-8"
    )


async def test_a_user_without_photos_gets_an_empty_list_and_the_upload_page(
    agent: Agent,
) -> None:
    token = await taras(agent)
    result = data(await call(agent, token, "list_photos"))
    assert result == {
        "photos": [],
        "suggested_photo_id": None,
        "photo_upload_url": f"{WEB}/profile/photos",
    }


async def test_photos_come_newest_first_with_days_and_web_previews(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await add_photo(agent, "taras@example.com", "first")
    await add_photo(agent, "taras@example.com", "second")

    result = data(await call(agent, token, "list_photos"))

    today = local_day(datetime.now(UTC))
    assert result["suggested_photo_id"] == 2
    assert result["photos"] == [
        {
            "photo_id": 2,
            "label": "second",
            "added": today,
            "last_used": None,
            "preview_url": f"{WEB}/api/photos/2.jpg",
        },
        {
            "photo_id": 1,
            "label": "first",
            "added": today,
            "last_used": None,
            "preview_url": f"{WEB}/api/photos/1.jpg",
        },
    ]


async def test_one_user_does_not_see_the_photos_of_another(agent: Agent) -> None:
    await add_photo(agent, "taras@example.com", "mine")
    other: dict[str, Any] = data(await call(agent, await katya(agent), "list_photos"))
    assert (other["photos"], other["suggested_photo_id"]) == ([], None)
