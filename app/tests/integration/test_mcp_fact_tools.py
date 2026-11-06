"""Тули фактів через SDK-клієнт: DCR → токен → `tools/list` і виклики на справжньому Postgres."""

from typing import Any

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from tests.integration.test_agent_http import PUBLIC, Agent
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

FACT_TOOLS = {
    "save_original_cv",
    "get_original_cv",
    "save_facts",
    "list_facts",
    "update_fact",
    "confirm_facts",
    "delete_fact",
}
PYTHON = {"kind": "skill", "text": "Python"}
LEAD = {"kind": "experience", "text": "Backend Lead at Acme, 2021–2024"}
LATENCY = {"kind": "achievement", "text": "Cut p95 latency by 40%"}


async def save(agent: Agent, token: str, *facts: dict[str, str]) -> dict[str, Any]:
    return data(await call(agent, token, "save_facts", {"facts": list(facts)}))


async def listed(agent: Agent, token: str, **arguments: Any) -> list[dict[str, Any]]:
    result = await call(agent, token, "list_facts", arguments)
    return list(data(result)["facts"])


async def test_tools_list_has_the_seven_fact_tools_with_the_catalog_descriptions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools) >= FACT_TOOLS
    for name in FACT_TOOLS:
        assert tools[name].description == (TOOLS / f"{name}.md").read_text(
            encoding="utf-8"
        )


async def test_save_facts_then_list_facts_returns_them_unconfirmed_by_kind(
    agent: Agent,
) -> None:
    token = await taras(agent)
    saved = await save(agent, token, PYTHON, LEAD)
    assert saved == {
        "added": [
            {
                "fact_id": 1,
                "kind": "skill",
                "text": "Python",
                "confirmed": False,
                "source": "cv",
                "job_id": None,
            },
            {
                "fact_id": 2,
                "kind": "experience",
                "text": LEAD["text"],
                "confirmed": False,
                "source": "cv",
                "job_id": None,
            },
        ],
        "skipped_duplicates": [],
    }
    assert [f["fact_id"] for f in await listed(agent, token)] == [2, 1]


async def test_save_facts_without_a_source_saves_cv_facts_unconfirmed(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await save(agent, token, PYTHON)
    (fact,) = await listed(agent, token)
    assert (fact["source"], fact["confirmed"], fact["job_id"]) == ("cv", False, None)


@pytest.mark.parametrize("source", ["cv", "chat", "manual"])
async def test_save_facts_keeps_the_given_source_and_leaves_the_fact_unconfirmed(
    agent: Agent, source: str
) -> None:
    token = await taras(agent)
    saved = data(
        await call(agent, token, "save_facts", {"facts": [PYTHON], "source": source})
    )
    assert [(f["source"], f["confirmed"]) for f in saved["added"]] == [(source, False)]
    assert [(f["source"], f["confirmed"]) for f in await listed(agent, token)] == [
        (source, False)
    ]


async def test_save_facts_with_an_unknown_source_is_refused_and_saves_nothing(
    agent: Agent,
) -> None:
    token = await taras(agent)
    result = await call(
        agent, token, "save_facts", {"facts": [PYTHON], "source": "linkedin"}
    )
    assert result.is_error is True
    assert await listed(agent, token) == []


async def test_duplicates_are_reported_and_the_rest_is_added(agent: Agent) -> None:
    token = await taras(agent)
    await save(agent, token, PYTHON)
    saved = await save(
        agent,
        token,
        LEAD,
        {"kind": "skill", "text": " PYTHON "},
        {"kind": "experience", "text": "python"},
        LEAD,
    )
    assert [f["fact_id"] for f in saved["added"]] == [2]
    assert saved["skipped_duplicates"] == ["PYTHON", "python", LEAD["text"]]


async def test_an_invalid_fact_rejects_the_whole_call(agent: Agent) -> None:
    token = await taras(agent)
    result = await call(
        agent,
        token,
        "save_facts",
        {"facts": [PYTHON, {"kind": "skill", "text": "x" * 501}]},
    )
    assert error_text(result).endswith(
        "Факт 2: Факт задовгий: більше 500 символів — розбий на кілька."
    )
    assert await listed(agent, token) == []


async def test_list_facts_filters_by_confirmation(agent: Agent) -> None:
    token = await taras(agent)
    await save(agent, token, PYTHON, LEAD)
    await call(agent, token, "confirm_facts", {"fact_ids": [1]})
    assert [f["fact_id"] for f in await listed(agent, token, confirmed=True)] == [1]
    assert [f["fact_id"] for f in await listed(agent, token, confirmed=False)] == [2]
    assert [f["fact_id"] for f in await listed(agent, token)] == [2, 1]
    assert [f["fact_id"] for f in await listed(agent, token, confirmed=None)] == [2, 1]


async def test_update_fact_makes_it_unconfirmed(agent: Agent) -> None:
    token = await taras(agent)
    await save(agent, token, PYTHON)
    await call(agent, token, "confirm_facts", {"fact_ids": [1]})
    updated = data(
        await call(
            agent,
            token,
            "update_fact",
            {
                "fact_id": 1,
                "fact": {"kind": "project", "text": "Python 3.14 migration"},
            },
        )
    )
    assert updated == {
        "fact_id": 1,
        "kind": "project",
        "text": "Python 3.14 migration",
        "confirmed": False,
        "source": "cv",
        "job_id": None,
    }
    assert [f["confirmed"] for f in await listed(agent, token)] == [False]


async def test_update_to_the_text_of_another_fact_is_an_error(agent: Agent) -> None:
    token = await taras(agent)
    await save(agent, token, PYTHON, LEAD)
    result = await call(agent, token, "update_fact", {"fact_id": 2, "fact": PYTHON})
    assert error_text(result).endswith("Такий факт уже є: #1.")


async def test_confirm_facts_returns_the_confirmed_ones(agent: Agent) -> None:
    token = await taras(agent)
    await save(agent, token, PYTHON, LEAD, LATENCY)
    confirmed = data(await call(agent, token, "confirm_facts", {"fact_ids": [3, 1]}))
    assert [(f["fact_id"], f["confirmed"]) for f in confirmed["facts"]] == [
        (1, True),
        (3, True),
    ]
    assert {f["fact_id"]: f["confirmed"] for f in await listed(agent, token)} == {
        3: True,
        2: False,
        1: True,
    }


async def test_confirm_with_an_unknown_id_is_an_error_and_changes_nothing(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await save(agent, token, PYTHON)
    result = await call(agent, token, "confirm_facts", {"fact_ids": [1, 99]})
    assert error_text(result).endswith("Факти не знайдено: #99.")
    assert [f["confirmed"] for f in await listed(agent, token)] == [False]


async def test_confirm_without_ids_is_an_error(agent: Agent) -> None:
    token = await taras(agent)
    result = await call(agent, token, "confirm_facts", {"fact_ids": []})
    assert error_text(result).endswith("Не вибрано жодного факту.")


async def test_delete_fact_returns_deleted_and_removes_it(agent: Agent) -> None:
    token = await taras(agent)
    await save(agent, token, PYTHON, LEAD)
    assert data(await call(agent, token, "delete_fact", {"fact_id": 2})) == {
        "deleted": 2
    }
    assert [f["fact_id"] for f in await listed(agent, token)] == [1]
    again = await call(agent, token, "delete_fact", {"fact_id": 2})
    assert error_text(again).endswith("Факт #2 не знайдено.")


async def test_save_original_cv_then_get_returns_text_name_and_day(
    agent: Agent,
) -> None:
    token = await taras(agent)
    saved = data(
        await call(
            agent,
            token,
            "save_original_cv",
            {"text": " Test User\nSenior Backend ", "file_name": "cv.pdf"},
        )
    )
    assert saved == {"saved": True}
    cv = data(await call(agent, token, "get_original_cv"))
    day = cv.pop("saved")
    assert len(day) == 10
    assert cv == {"file_name": "cv.pdf", "text": "Test User\nSenior Backend"}


async def test_a_new_cv_replaces_the_old_one_and_keeps_the_facts(agent: Agent) -> None:
    token = await taras(agent)
    await save(agent, token, PYTHON)
    await call(agent, token, "save_original_cv", {"text": "old", "file_name": "a.pdf"})
    await call(agent, token, "save_original_cv", {"text": "new"})
    cv = data(await call(agent, token, "get_original_cv"))
    assert (cv["text"], cv["file_name"]) == ("new", None)
    assert len(await listed(agent, token)) == 1


async def test_reading_a_missing_cv_is_an_error(agent: Agent) -> None:
    result = await call(agent, await taras(agent), "get_original_cv")
    assert error_text(result).endswith("Original CV ще не збережено.")


async def test_an_invalid_cv_is_an_error_and_keeps_the_saved_one(agent: Agent) -> None:
    token = await taras(agent)
    await call(agent, token, "save_original_cv", {"text": "keep"})
    result = await call(agent, token, "save_original_cv", {"text": "x" * 50_001})
    assert error_text(result).endswith("CV задовге: більше 50000 символів.")
    assert data(await call(agent, token, "get_original_cv"))["text"] == "keep"


async def test_one_user_does_not_see_or_change_the_facts_of_another(
    agent: Agent,
) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    await save(agent, taras_token, PYTHON, LEAD)
    await call(agent, taras_token, "save_original_cv", {"text": "secret"})
    assert await listed(agent, katya_token) == []
    missing = await call(agent, katya_token, "get_original_cv")
    assert error_text(missing).endswith("Original CV ще не збережено.")
    for name, arguments in (
        ("confirm_facts", {"fact_ids": [1]}),
        ("update_fact", {"fact_id": 1, "fact": LEAD}),
        ("delete_fact", {"fact_id": 1}),
    ):
        assert (await call(agent, katya_token, name, arguments)).is_error is True
    assert (await save(agent, katya_token, PYTHON))["added"][0]["fact_id"] == 1
    assert [f["confirmed"] for f in await listed(agent, taras_token)] == [False, False]
    assert len(await listed(agent, taras_token)) == 2
