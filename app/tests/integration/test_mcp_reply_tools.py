"""Тули відповідей через SDK-клієнт: DCR → токен → синк пошти → `list_replies` / `review_reply` на справжньому Postgres."""

from datetime import UTC, datetime
from typing import Any

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from tests.integration.test_agent_http import PUBLIC, Agent
from tests.integration.test_mcp_application_tools import mark, move
from tests.integration.test_mcp_job_tools import add, data, error_text
from tests.integration.test_mcp_mail_tools import agent, deliver, inbox, letter
from tests.integration.test_mcp_profile_tools import (
    TOOLS,
    anyio_backend,
    call,
    get_profile,
    katya,
    taras,
    update_profile,
)

__all__ = ["agent", "anyio_backend"]

pytestmark = pytest.mark.anyio

REPLY_TOOLS = {"list_replies", "review_reply"}
SUMMER = datetime(2026, 7, 1, 10, 5, tzinfo=UTC)
FORWARDED = (
    "---------- Forwarded message ---------\n"
    "From: Ana Recruiter <ana.recruiter@acme.example>\n"
    "Date: Mon, Oct 19, 2026 at 10:15 AM\n"
    "Subject: Message replied: Backend\n"
    "To: Owner <owner@owner.example>\n\n"
    "Unfortunately, we are not moving forward."
)


def one(items: list[dict[str, Any]]) -> dict[str, Any]:
    assert len(items) == 1, items
    return items[0]


async def listed(agent: Agent, token: str, **arguments: Any) -> list[dict[str, Any]]:
    return list(data(await call(agent, token, "list_replies", arguments))["replies"])


async def review(
    agent: Agent, token: str, reply_id: int, kind: str, job_id: int | None = None
) -> Any:
    arguments = {"reply_id": reply_id, "type": kind, "job_id": job_id}
    return await call(agent, token, "review_reply", arguments)


async def applied_job(agent: Agent, token: str, **application: Any) -> None:
    """Вакансія 1 «Backend / Acme», подана з доменом acme.example."""
    await add(agent, token, title="Backend", company="Acme")
    await mark(agent, token, company_domains=["acme.example"], **application)


async def arrive(agent: Agent, token: str, *mails: Any) -> str:
    """Адреса користувача, перший порожній синк (курсор) і листи як зміни."""
    address = (await inbox(agent, token))["forwarding_address"]
    await deliver(agent)
    await deliver(agent, *(make(address) for make in mails))
    return str(address)


def mail_from(gmail_id: str, **fields: Any) -> Any:
    return lambda address: letter(gmail_id, address, **fields)


async def status_of(agent: Agent, token: str, job_id: int = 1) -> str:
    view = data(await call(agent, token, "get_job", {"job_id": job_id}))
    return str(view["application"]["status"])


async def test_tools_list_has_both_reply_tools_with_the_catalog_descriptions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools) >= REPLY_TOOLS
    for name in REPLY_TOOLS:
        assert tools[name].description == (TOOLS / f"{name}.md").read_text(
            encoding="utf-8"
        )


async def test_a_synced_company_reply_is_listed_matched_and_moves_the_application(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await applied_job(agent, token)
    await arrive(
        agent,
        token,
        mail_from(
            "m1",
            name="María",
            subject="Backend: next steps",
            text="Unfortunately, we are not moving forward.",
            received_at=SUMMER,
        ),
    )

    result = data(await call(agent, token, "list_replies"))

    reply = one(result["replies"])
    reply_id = reply.pop("reply_id")
    assert reply_id >= 1
    assert reply == {
        "received": "2026-07-01 12:05",
        "from_address": "talent@acme.example",
        "sender_auth": "verified",
        "untrusted_from_name": "María",
        "untrusted_subject": "Backend: next steps",
        "untrusted_text": "Unfortunately, we are not moving forward.",
        "text_clipped": False,
        "job": {
            "job_id": 1,
            "title": "Backend",
            "company": "Acme",
            "status": "replied",
        },
        "confidence": "high",
        "matched_by": "domain",
        "suggested_type": "rejection",
        "type": None,
        "manual_forward": None,
    }
    assert result["rules"].startswith("Review each reply with the user, one by one.")
    assert await status_of(agent, token) == "replied"


async def test_rules_are_the_prompt_file(agent: Agent) -> None:
    token = await taras(agent)

    rules = data(await call(agent, token, "list_replies"))["rules"]

    assert rules == (TOOLS.parent.parent / "mail" / "review_rules.md").read_text(
        encoding="utf-8"
    )


async def test_a_long_text_is_clipped_to_4000_characters_and_flagged(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await arrive(agent, token, mail_from("m1", text="x" * 4001))

    reply = one(await listed(agent, token))

    assert len(reply["untrusted_text"]) == 4000
    assert reply["text_clipped"] is True


async def test_listing_has_unreviewed_by_default_newest_first_and_a_limit(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await arrive(
        agent,
        token,
        mail_from("m1", received_at=datetime(2026, 10, 20, 8, tzinfo=UTC)),
        mail_from("m2", received_at=datetime(2026, 10, 21, 8, tzinfo=UTC)),
        mail_from("m3", received_at=datetime(2026, 10, 22, 8, tzinfo=UTC)),
    )
    newest = await listed(agent, token, limit=2)
    assert len(newest) == 2
    first = newest[0]
    await review(agent, token, first["reply_id"], "other")

    fresh = await listed(agent, token)
    done = await listed(agent, token, reviewed=True)

    assert [r["untrusted_subject"] for r in fresh] == ["Re: m2", "Re: m1"]
    assert [r["untrusted_subject"] for r in done] == ["Re: m3"]
    assert len(await listed(agent, token, limit=1)) == 1


@pytest.mark.parametrize("limit", [0, 51])
async def test_a_limit_outside_1_to_50_is_refused(agent: Agent, limit: int) -> None:
    result = await call(agent, await taras(agent), "list_replies", {"limit": limit})

    assert "Unknown tool" not in error_text(result)


@pytest.mark.parametrize(
    ("kind", "status"),
    [
        ("rejection", "rejected"),
        ("invitation", "interview"),
        ("assignment", "interview"),
        ("other", "replied"),
        ("auto_confirmation", "applied"),
    ],
)
async def test_review_moves_the_application_by_the_type_and_returns_both_views(
    agent: Agent, kind: str, status: str
) -> None:
    token = await taras(agent)
    await applied_job(agent, token)
    # Лист без підтвердження DMARC: зіставлено, але подача ще applied.
    await arrive(agent, token, mail_from("m1", dmarc="none"))
    reply = one(await listed(agent, token))
    assert await status_of(agent, token) == "applied"

    result = data(await review(agent, token, reply["reply_id"], kind, 1))

    assert result["reply"]["type"] == kind
    assert result["reply"]["job"]["job_id"] == 1
    assert result["application"]["job_id"] == 1
    assert result["application"]["status"] == status
    assert await listed(agent, token) == []
    assert [r["type"] for r in await listed(agent, token, reviewed=True)] == [kind]


async def test_review_without_a_job_says_the_mail_is_not_about_an_application(
    agent: Agent,
) -> None:
    token = await taras(agent)
    await arrive(agent, token, mail_from("m1"))
    reply = one(await listed(agent, token))

    result = data(await review(agent, token, reply["reply_id"], "other"))

    assert result["application"] is None
    assert result["reply"]["job"] is None


async def test_review_errors_have_the_v1_texts(agent: Agent) -> None:
    token = await taras(agent)
    await add(agent, token, title="Data", company="Bolt")
    await arrive(agent, token, mail_from("m1"))
    reply = one(await listed(agent, token))

    unknown = await review(agent, token, 999, "other")
    no_application = await review(agent, token, reply["reply_id"], "other", 1)
    bad_type = await review(agent, token, reply["reply_id"], "ghosted")

    assert "Відповідь 999 не знайдено." in error_text(unknown)
    assert "Подачі на вакансію 1 нема: спершу mark_applied." in error_text(
        no_application
    )
    assert bad_type.is_error is True


async def test_a_status_never_moves_back_through_review(agent: Agent) -> None:
    token = await taras(agent)
    await applied_job(agent, token)
    await move(agent, token, "offer")
    await arrive(agent, token, mail_from("m1", dmarc="none"))
    reply = one(await listed(agent, token))

    result = data(await review(agent, token, reply["reply_id"], "rejection", 1))

    assert result["application"]["status"] == "offer"


async def test_another_user_neither_sees_nor_reviews_my_replies(agent: Agent) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    await applied_job(agent, taras_token)
    await arrive(agent, taras_token, mail_from("m1", dmarc="none"))
    mine = one(await listed(agent, taras_token))

    seen = await listed(agent, katya_token)
    reviewed = await review(agent, katya_token, mine["reply_id"], "rejection")

    assert seen == []
    assert f"Відповідь {mine['reply_id']} не знайдено." in error_text(reviewed)
    assert await status_of(agent, taras_token) == "applied"
    assert [r["type"] for r in await listed(agent, taras_token)] == [None]


async def test_a_manual_forward_is_marked_in_the_replies_and_in_the_mail_inbox(
    agent: Agent,
) -> None:
    token = await taras(agent)
    profile = await get_profile(agent, token)
    await update_profile(agent, token, profile | {"email": "owner@owner.example"})
    await applied_job(agent, token)
    await arrive(
        agent,
        token,
        mail_from(
            "f1",
            sender="owner@owner.example",
            name="Owner",
            subject="Fwd: Message replied",
            text=FORWARDED,
        ),
    )

    reply = one(await listed(agent, token))
    recent = one((await inbox(agent, token))["recent"])

    expected = {
        "untrusted_from_address": "ana.recruiter@acme.example",
        "untrusted_from_name": "Ana Recruiter",
        "untrusted_subject": "Message replied: Backend",
    }
    assert reply["manual_forward"] == expected
    assert recent["manual_forward"] == expected
    assert reply["suggested_type"] == "rejection"
    assert reply["job"]["job_id"] == 1
    # Відправник із блоку не перевірений: автостатусу нема.
    assert await status_of(agent, token) == "applied"
