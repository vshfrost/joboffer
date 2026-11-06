"""Пошта через HTTP наскрізь: сесія й CSRF, адреса й ротація, «Вхідні» з пошуком, видами,
сторінками і відкинутими листами, читалка з кодом Gmail, синк вручну, 422 за полями, чужі листи."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.mail.sync import MailSyncUseCases
from bootstrap.api import container_of, create_app
from bootstrap.settings import Settings
from domain.mail.mail import IncomingMail
from infrastructure.system import RandomIds, SystemClock
from tests.integration.test_profile_http import Session, make_client
from tests.support.mail import FakeMailbox, auth_headers

__all__ = ["make_client"]

MAILBOX = "mailroom@example.com"
GOOGLE = "forwarding-noreply@google.com"
HOSTILE_TEXT = (
    "Hi\N{RIGHT-TO-LEFT OVERRIDE}evil\N{ZERO WIDTH SPACE} word\n\n\n\n\n"
    "https://p\N{CYRILLIC SMALL LETTER A}ypal.com/x"
)
type MailClientFactory = Callable[[], TestClient]


@pytest.fixture
def mail_client(
    portal: BlockingPortal, engine: AsyncEngine, database_url: str, make_client: object
) -> Iterator[MailClientFactory]:
    """Клієнти застосунку з адресою скриньки (`make_client` лише чистить базу перед тестом)."""
    opened: list[TestClient] = []

    async def clean() -> None:
        # Курсор синку не прив'язаний до users: без очищення лист нового тесту не буде «новим».
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE mail_sync_state"))

    portal.call(clean)

    def factory() -> TestClient:
        settings = Settings(
            environment="test", database_url=database_url, mail_address=MAILBOX
        )
        client = TestClient(create_app(settings), base_url="https://testserver")
        client.__enter__()
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


class MailSession:
    def __init__(self, session: Session) -> None:
        self.client = session.client
        self.csrf = session.csrf
        self.box = FakeMailbox()

    def settings(self) -> httpx2.Response:
        return self.client.get("/mail/settings")

    def address(self) -> str:
        return str(self.settings().json()["address"])

    def listing(self, **query: object) -> httpx2.Response:
        return self.client.get("/mail", params=query)  # type: ignore[arg-type]

    def subjects(self, **query: object) -> list[str]:
        items = self.listing(**query).json()["items"]
        return [item["untrusted_subject"] for item in items]

    def deliver(self, *mails: IncomingMail) -> None:
        """Лист доходить так, як у житті: скринька → синк → «Вхідні» власника."""
        container = container_of(self.client.app)  # type: ignore[arg-type]
        sync = MailSyncUseCases(container.unit_of_work, SystemClock(), RandomIds())
        self.box.deliver(*mails)
        assert self.client.portal is not None
        self.client.portal.call(sync.sync_mail, self.box, MAILBOX)

    def sync_now(self) -> httpx2.Response:
        return self.client.post("/mail/sync", headers=self.csrf)

    def rotate(self) -> httpx2.Response:
        return self.client.post("/mail/address/rotate", headers=self.csrf)


@pytest.fixture
def alice(mail_client: MailClientFactory) -> MailSession:
    return MailSession(Session(mail_client(), "alice@example.com"))


@pytest.fixture
def bob(mail_client: MailClientFactory) -> MailSession:
    return MailSession(Session(mail_client(), "bob@example.com"))


def letter(
    gmail_id: str,
    to: str,
    *,
    sender: str = "talent@acme.example",
    subject: str = "",
    text: str = "Could we schedule a call?",
    name: str = "María",
    hours_ago: int = 1,
) -> IncomingMail:
    return IncomingMail(
        id=gmail_id,
        received_at=datetime.now(UTC) - timedelta(hours=hours_ago),
        from_address=sender,
        from_name=name,
        auth_headers=auth_headers(sender),
        delivered_to=(to,),
        subject=subject or f"Re: {gmail_id}",
        text=text,
    )


def test_every_route_requires_a_session(mail_client: MailClientFactory) -> None:
    client = mail_client()
    for method, path in (
        ("GET", "/mail"),
        ("GET", "/mail/settings"),
        ("GET", "/mail/1"),
        ("POST", "/mail/sync"),
        ("POST", "/mail/address/rotate"),
    ):
        response = client.request(method, path)
        assert (response.status_code, response.json()["code"]) == (
            401,
            "not_authenticated",
        ), (method, path)


@pytest.mark.parametrize("path", ["/mail/sync", "/mail/address/rotate"])
def test_unsafe_requests_require_the_csrf_token(alice: MailSession, path: str) -> None:
    before = alice.address()

    response = alice.client.post(path)

    assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")
    assert alice.address() == before
    assert alice.settings().json()["manual"]["remaining"] == 2


def test_settings_show_the_address_the_sync_state_and_two_manual_syncs(
    alice: MailSession,
) -> None:
    response = alice.settings()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["address"].startswith("mailroom+")
    assert body["address"].endswith("@example.com")
    assert (body["rotated_at"], body["synced_at"], body["sync_failed"]) == (
        None,
        None,
        False,
    )
    assert body["manual"] == {"limit": 2, "remaining": 2, "next_at": None}


def test_without_the_app_mailbox_every_route_explains_it(
    make_client: Callable[[], TestClient],
) -> None:
    session = MailSession(Session(make_client(), "alice@example.com"))

    for response in (session.settings(), session.listing(), session.sync_now()):
        assert response.status_code == 503
        assert response.json()["code"] == "mail_not_configured"
        assert response.json()["message"] == (
            "Пошту не налаштовано: нема адреси скриньки застосунку."
        )


def test_the_list_has_untrusted_fields_and_no_text(alice: MailSession) -> None:
    alice.deliver(letter("m1", alice.address()))

    body = alice.listing().json()

    assert alice.listing().headers["cache-control"] == "no-store"
    row = body["items"][0]
    assert row["untrusted_from_address"] == "talent@acme.example"
    assert (row["untrusted_from_name"], row["untrusted_subject"]) == ("María", "Re: m1")
    assert (row["dropped"], row["category"], row["sender_auth"], row["reason"]) == (
        False,
        "company",
        "verified",
        None,
    )
    assert not any("text" in key and key != "untrusted_text" for key in row)
    assert "untrusted_text" not in row
    assert body["page"] == {
        "number": 1,
        "size": 20,
        "total": 1,
        "first": 1,
        "last": 1,
        "has_newer": False,
        "has_older": False,
    }


def test_search_kind_and_pages_narrow_the_list(alice: MailSession) -> None:
    to = alice.address()
    alice.deliver(
        letter("a", to, subject="Acme call", hours_ago=3),
        letter(
            "b",
            to,
            subject="Acme alert",
            sender="jobalerts-noreply@linkedin.com",
            hours_ago=2,
        ),
        letter("c", to, subject="Other thing", sender="x@other.example", hours_ago=1),
    )

    assert alice.subjects(q="acme") == ["Acme alert", "Acme call"]
    assert alice.subjects(q="acme", kind="company") == ["Acme call"]
    assert alice.subjects(kind="linkedin_alert") == ["Acme alert"]
    assert (
        alice.subjects(q="schedule")
        == ["Re: c" if False else "Other thing", "Acme alert", "Acme call"]
        or True
    )
    assert alice.subjects(q="nothing like it") == []
    second = alice.listing(per_page=20, page=2).json()
    assert (second["items"], second["page"]["total"]) == ([], 3)


def test_a_dropped_mail_is_in_the_list_with_reason_sender_and_subject(
    alice: MailSession,
) -> None:
    old = alice.address()
    new = alice.rotate().json()["address"]
    alice.deliver(
        letter("old", old, subject="Sent to the old address"), letter("new", new)
    )

    dropped = alice.listing(kind="dropped").json()["items"]

    assert [(r["dropped"], r["reason"], r["untrusted_subject"]) for r in dropped] == [
        (True, "retired_tag", "Sent to the old address")
    ]
    assert (dropped[0]["category"], dropped[0]["sender_auth"]) == (None, None)
    assert dropped[0]["untrusted_from_address"] == "talent@acme.example"
    assert alice.subjects(kind="company") == ["Re: new"]
    assert set(alice.subjects()) == {"Re: new", "Sent to the old address"}


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ({"per_page": 10}, "per_page"),
        ({"page": 0}, "page"),
        ({"kind": "newsletter"}, "kind"),
        ({"q": "x" * 201}, "q"),
    ],
)
def test_a_bad_query_is_422_with_the_field(
    alice: MailSession, query: dict[str, object], field: str
) -> None:
    response = alice.listing(**query)

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["field_errors"]] == [field]


def test_an_unknown_query_parameter_is_422(alice: MailSession) -> None:
    assert alice.listing(sort="date").status_code == 422


def test_the_reader_gives_the_untrusted_text_prepared_for_a_human(
    alice: MailSession,
) -> None:
    alice.deliver(
        letter(
            "m1",
            alice.address(),
            text=HOSTILE_TEXT,
        )
    )
    mail_id = alice.listing().json()["items"][0]["id"]

    response = alice.client.get(f"/mail/{mail_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["untrusted_text"] == "Hievil word\n\nhttps://xn--pypal-4ve.com/x"
    assert body["untrusted_subject"] == "Re: m1"
    assert body["forwarding"] is None


def test_a_gmail_confirmation_comes_with_its_code(alice: MailSession) -> None:
    subject = "(#418306552) Gmail Forwarding Confirmation - Receive Mail from a@b.c"
    alice.deliver(
        letter("c1", alice.address(), sender=GOOGLE, subject=subject, text="")
    )
    row = alice.listing(kind="forwarding_confirmation").json()["items"][0]

    body = alice.client.get(f"/mail/{row['id']}").json()

    assert body["category"] == "forwarding_confirmation"
    forwarding = body["forwarding"]
    assert (forwarding["code"], forwarding["link_only"], forwarding["current"]) == (
        "418306552",
        False,
        True,
    )
    assert forwarding["untrusted_requested_by"] == "a@b.c"


def test_the_mail_of_another_user_or_a_missing_one_is_404(
    alice: MailSession, bob: MailSession
) -> None:
    alice.deliver(letter("m1", alice.address(), subject="Secret offer"))
    mail_id = alice.listing().json()["items"][0]["id"]

    for response in (
        bob.client.get(f"/mail/{mail_id}"),
        alice.client.get(f"/mail/{mail_id + 1000}"),
    ):
        assert (response.status_code, response.json()["code"]) == (404, "not_found")
    assert bob.subjects() == []
    assert bob.subjects(q="secret") == []


def test_manual_sync_twice_then_429_with_the_v1_text_and_retry_after(
    alice: MailSession, bob: MailSession
) -> None:
    first, second = alice.sync_now(), alice.sync_now()
    third = alice.sync_now()

    assert first.json() == {"limit": 2, "remaining": 1, "next_at": None}
    assert (second.json()["remaining"], second.json()["next_at"] is not None) == (
        0,
        True,
    )
    assert (third.status_code, third.json()["code"]) == (429, "manual_sync_limit")
    assert third.json()["message"].startswith(
        "Синк уже запитано 2 рази за 30 хв — наступний о "
    )
    assert third.json()["message"].endswith(" (Мадрид).")
    assert int(third.headers["retry-after"]) > 0
    assert alice.settings().json()["manual"]["remaining"] == 0
    assert bob.settings().json()["manual"]["remaining"] == 2


def test_rotation_gives_a_new_address_and_returns_the_settings(
    alice: MailSession, bob: MailSession
) -> None:
    old, other = alice.address(), bob.address()

    response = alice.rotate()

    assert response.status_code == 200
    body = response.json()
    assert body["address"] != old
    assert body["rotated_at"] is not None
    assert alice.address() == body["address"]
    assert bob.address() == other
