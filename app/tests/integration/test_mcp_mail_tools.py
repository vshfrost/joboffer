"""Тул `get_mail_inbox` через SDK-клієнт: DCR → токен → виклик на справжньому Postgres."""

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.identity import CreateUser
from application.mail.sync import MailSyncUseCases
from bootstrap.agent import create_agent_app
from bootstrap.container import Container
from bootstrap.settings import Settings
from domain.identity.ids import UserId
from domain.mail.mail import IncomingMail
from infrastructure.system import RandomIds, SystemClock
from tests.integration.test_agent_http import (
    BASE,
    OTHER_PASSWORD,
    PASSWORD,
    PUBLIC,
    Agent,
)
from tests.integration.test_mcp_job_tools import data, error_text
from tests.integration.test_mcp_profile_tools import (
    TOOLS,
    anyio_backend,
    call,
    katya,
    taras,
)
from tests.support.mail import FakeMailbox, auth_headers

__all__ = ["anyio_backend"]

pytestmark = pytest.mark.anyio

MAILBOX = "mailroom@example.com"
GOOGLE = "forwarding-noreply@google.com"


@pytest.fixture
async def agent(
    portal: BlockingPortal, engine: AsyncEngine, database_url: str
) -> AsyncIterator[Agent]:
    """Агент зі стандартним набором тулів і адресою скриньки застосунку."""

    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
            await conn.execute(text("TRUNCATE oauth_clients CASCADE"))
            await conn.execute(text("TRUNCATE login_failures"))
            await conn.execute(text("TRUNCATE mail_sync_state"))

    portal.call(clean)
    app = create_agent_app(
        Settings(
            environment="test",
            database_url=database_url,
            web_public_url=BASE,
            mail_address=MAILBOX,
        )
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


async def inbox(agent: Agent, token: str) -> dict[str, Any]:
    result = await call(agent, token, "get_mail_inbox")
    assert result.is_error is False, result
    return data(result)


async def deliver(agent: Agent, *mails: IncomingMail) -> None:
    box = FakeMailbox()
    box.deliver(*mails)
    sync = MailSyncUseCases(agent.container.unit_of_work, SystemClock(), RandomIds())
    await sync.sync_mail(box, MAILBOX)


def letter(gmail_id: str, to: str, **fields: Any) -> IncomingMail:
    sender = fields.pop("sender", "talent@acme.example")
    dmarc = fields.pop("dmarc", "pass")
    return IncomingMail(
        id=gmail_id,
        received_at=fields.pop("received_at", datetime.now(UTC) - timedelta(hours=1)),
        from_address=sender,
        from_name=fields.pop("name", "María"),
        auth_headers=auth_headers(sender, dmarc),
        delivered_to=(to,),
        subject=fields.pop("subject", f"Re: {gmail_id}"),
        text=fields.pop("text", "Could we schedule a call?"),
        **fields,
    )


async def test_tools_list_has_get_mail_inbox_with_the_catalog_description(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert tools["get_mail_inbox"].description == (
        TOOLS / "get_mail_inbox.md"
    ).read_text(encoding="utf-8")


async def test_a_new_user_gets_an_address_and_an_empty_inbox(agent: Agent) -> None:
    view = await inbox(agent, await taras(agent))

    assert view["forwarding_address"].startswith("mailroom+")
    assert view["forwarding_address"].endswith("@example.com")
    assert view["forwarding_code"] is None
    assert view["forwarding_link_only"] is False
    assert view["recent"] == []
    assert (view["last_synced"], view["sync_failed"]) == (None, False)
    assert view["daily_limit_drops"] == {"count": 0, "last_received": None}
    assert view["settings_url"] == f"{BASE}/profile/mail"


async def test_the_inbox_gives_untrusted_mail_the_code_and_the_madrid_time(
    agent: Agent,
) -> None:
    token = await taras(agent)
    address = (await inbox(agent, token))["forwarding_address"]
    received = datetime(2026, 7, 1, 10, 5, tzinfo=UTC)
    # Перший синк читає лише останні 90 днів; лист за 1 липня приходить уже як зміна.
    await deliver(agent)
    subject = "(#418306552) Gmail Forwarding Confirmation - Receive Mail from a@b.c"
    await deliver(
        agent,
        letter(
            "c1", address, sender=GOOGLE, subject=subject, text="", received_at=received
        ),
        letter("m1", address, name="María", subject="Re: next steps"),
    )

    view = await inbox(agent, token)

    assert view["forwarding_code"] == "418306552"
    assert (view["forwarding_link_only"], view["forwarding_requested_by"]) == (
        False,
        "a@b.c",
    )
    first, second = view["recent"]
    assert (first["from_address"], first["untrusted_from_name"]) == (
        "talent@acme.example",
        "María",
    )
    assert (first["untrusted_subject"], first["category"]) == (
        "Re: next steps",
        "company",
    )
    assert first["sender_auth"] == "verified"
    assert first["manual_forward"] is None
    assert second["category"] == "forwarding_confirmation"
    assert second["received"] == "2026-07-01 12:05"  # літній час Мадрида: UTC+2
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d", view["last_synced"])


async def test_a_confirmation_without_a_code_is_link_only(agent: Agent) -> None:
    token = await taras(agent)
    address = (await inbox(agent, token))["forwarding_address"]
    await deliver(
        agent,
        letter(
            "c1",
            address,
            sender=GOOGLE,
            subject="Gmail Forwarding Confirmation",
            text="taras@example.com has requested to forward mail. Follow the link.",
        ),
    )

    view = await inbox(agent, token)

    assert view["forwarding_code"] is None
    assert view["forwarding_link_only"] is True
    assert view["forwarding_requested_by"] == "taras@example.com"


async def test_drops_and_forged_mail_are_counted_for_their_owner_only(
    agent: Agent,
) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    old = (await inbox(agent, taras_token))["forwarding_address"]
    await inbox(agent, katya_token)
    # Ротацію робить сам користувач у вебі; тут — прямо через use case.
    actor = Actor(
        user_id=UserId(UUID(agent.user_ids["taras@example.com"])),
        channel=Channel.WEB,
        client_id="web",
        grant_id=None,
        scopes=frozenset(Scope),
        correlation_id="test",
    )
    await agent.container.mail.rotate_address(actor)
    new = (await inbox(agent, taras_token))["forwarding_address"]
    assert new != old
    await deliver(agent, letter("old1", old), letter("f1", new, dmarc="fail"))

    mine = await inbox(agent, taras_token)
    theirs = await inbox(agent, katya_token)

    assert mine["old_address_drops"]["count"] == 1
    assert theirs["old_address_drops"] == {"count": 0, "last_received": None}
    assert [m["untrusted_subject"] for m in mine["recent"]] == ["Re: f1"]
    assert theirs["recent"] == []
    assert mine["suspicious_mail"]["count"] == 1
    assert theirs["suspicious_mail"] == {"count": 0, "last_received": None}


async def test_the_inbox_stays_at_the_twenty_latest_mails(agent: Agent) -> None:
    token = await taras(agent)
    address = (await inbox(agent, token))["forwarding_address"]
    await deliver(
        agent,
        *(
            letter(f"m{n}", address, received_at=datetime.now(UTC) - timedelta(hours=n))
            for n in range(1, 26)
        ),
    )

    view = await inbox(agent, token)

    assert len(view["recent"]) == 20
    assert view["recent"][0]["untrusted_subject"] == "Re: m1"


async def test_without_the_app_mailbox_the_tool_says_so(
    portal: BlockingPortal, engine: AsyncEngine, database_url: str
) -> None:
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
        created = await container.identity.create_user(
            CreateUser(
                email="taras@example.com", display_name="Користувач", password=PASSWORD
            )
        )
        bare = Agent(app, http, container, {"taras@example.com": created.id})
        result = await call(bare, await taras(bare), "get_mail_inbox")

    assert result.is_error is True
    assert "Пошту не налаштовано: нема адреси скриньки застосунку." in error_text(
        result
    )
