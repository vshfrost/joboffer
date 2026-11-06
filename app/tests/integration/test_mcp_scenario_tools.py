"""`get_scenario` через SDK-клієнт: DCR → токен → виклики на справжньому Postgres."""

from typing import Any

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from tests.integration.test_agent_http import PUBLIC, Agent
from tests.integration.test_mcp_analysis_tools import save, seed
from tests.integration.test_mcp_gap_answer_tools import GO_FACT, analysed, answer
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

PROMPTS = TOOLS.parents[1]
TAIL = (PROMPTS / "scenarios" / "next_step.md").read_text(encoding="utf-8")
REQUESTS = PROMPTS / "requests"
NAMES = ["add_job", "analysis", "gaps", "reanalysis", "cv", "cover_letter", "apply"]


async def scenario(
    agent: Agent, token: str, name: str, job_id: int | None = None
) -> Any:
    arguments: dict[str, Any] = {"name": name}
    if job_id is not None:
        arguments["job_id"] = job_id
    return await call(agent, token, "get_scenario", arguments)


async def test_tools_list_has_get_scenario_with_the_catalog_description(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert tools["get_scenario"].description == (TOOLS / "get_scenario.md").read_text(
        encoding="utf-8"
    )


async def test_add_job_needs_no_job_id_and_offers_the_analysis(agent: Agent) -> None:
    token = await taras(agent)

    result = data(await scenario(agent, token, "add_job"))

    assert result["name"] == "add_job"
    assert result["next"] == "analysis"
    assert result["skip_reason"] is None
    assert result["prompt"] == (
        (REQUESTS / "add_job.md").read_text(encoding="utf-8") + "\n\n" + TAIL
    )


async def test_an_unknown_scenario_is_an_error_listing_the_valid_names(
    agent: Agent,
) -> None:
    token = await taras(agent)

    message = error_text(await scenario(agent, token, "interview"))

    for name in NAMES:
        assert name in message


async def test_a_nonexistent_job_is_not_found(agent: Agent) -> None:
    token = await taras(agent)

    message = error_text(await scenario(agent, token, "analysis", 99))

    assert message.endswith("Вакансію 99 не знайдено.")


async def test_a_foreign_job_is_not_found(agent: Agent) -> None:
    number = await seed(agent)
    token = await katya(agent)

    message = error_text(await scenario(agent, token, "analysis", number))

    assert message.endswith(f"Вакансію {number} не знайдено.")


async def test_the_prompt_names_the_job_and_ends_with_the_tail(agent: Agent) -> None:
    token = await taras(agent)
    number = await seed(agent)

    result = data(await scenario(agent, token, "cv", number))

    assert f"job #{number}" in result["prompt"]
    assert "{job_id}" not in result["prompt"]
    assert result["prompt"].endswith(TAIL)
    assert result["next"] == "cover_letter"


async def test_apply_has_no_tail_and_nothing_after_it(agent: Agent) -> None:
    token = await taras(agent)
    number = await seed(agent)

    result = data(await scenario(agent, token, "apply", number))

    assert result["next"] is None
    assert TAIL not in result["prompt"]


async def test_gaps_are_required_while_a_gap_is_open(agent: Agent) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)

    gaps = data(await scenario(agent, token, "gaps", number))
    after_analysis = data(await scenario(agent, token, "analysis", number))

    assert gaps["skip_reason"] is None
    assert after_analysis["next"] == "gaps"


async def test_gaps_are_skipped_when_the_analysis_has_none(agent: Agent) -> None:
    token = await taras(agent)
    number = await seed(agent)
    await save(agent, token, number)

    gaps = data(await scenario(agent, token, "gaps", number))
    after_analysis = data(await scenario(agent, token, "analysis", number))

    assert gaps["skip_reason"] == "no open gaps"
    assert after_analysis["next"] == "cv"


async def test_a_fresh_analysis_skips_the_reanalysis(agent: Agent) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)

    result = data(await scenario(agent, token, "reanalysis", number))

    assert result["skip_reason"] == "the analysis is not stale"
    assert result["next"] == "cv"


async def test_a_stale_analysis_requires_the_reanalysis(agent: Agent) -> None:
    token = await taras(agent)
    number = await analysed(agent, token)
    await answer(agent, token, number, 1, True, [GO_FACT])

    result = data(await scenario(agent, token, "reanalysis", number))
    gaps = data(await scenario(agent, token, "gaps", number))

    assert result["skip_reason"] is None
    assert gaps["next"] == "reanalysis"
