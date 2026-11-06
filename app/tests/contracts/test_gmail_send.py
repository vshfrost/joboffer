"""Адаптер Gmail messages.send через httpx2 MockTransport і фейковий токен-ендпоінт Google:
без мережі. Лист — text/plain UTF-8 від «joboffer <скринька>», тема UTF-8, без посилань;
збій Google — `MailUnavailable` без тексту відповіді Google."""

import base64
import email
import json
from collections.abc import Callable
from email import policy
from email.message import EmailMessage
from pathlib import Path

import httpx2
import pytest
from anyio.from_thread import BlockingPortal

from application.mail.outgoing import OutgoingMailServices, OutgoingMailUseCases
from domain.mail.outgoing import MailQuotaExceeded, MailUnavailable, OutgoingMail
from infrastructure.gmail.client import OAUTH_URL, GmailCredentials
from infrastructure.gmail.sender import GMAIL_SEND_SCOPE, GmailSender
from infrastructure.templates.catalog import FileTemplates
from tests.support.clock import FakeClock
from tests.support.outgoing import (
    FakeAudit,
    InMemorySendUnitOfWork,
    SendStore,
)

SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
MAILROOM = "mailroom@example.com"
FAKE_SECRET = "client-secret"  # фейкові креди, мережі в тестах нема
FAKE_SEND_REFRESH = "send-refresh-token"
GOOGLE_ERROR_TEXT = "GOOGLE-SAYS-your-address-is-bad"
TEMPLATES = Path(__file__).parents[2] / "templates"
type Handler = Callable[[httpx2.Request], httpx2.Response]


class FakeGoogle:
    """Токен-ендпоінт і messages.send в одному: запити записуються."""

    def __init__(self, *, send_status: int = 200, token_status: int = 200) -> None:
        self.send_status = send_status
        self.token_status = token_status
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if str(request.url) == OAUTH_URL:
            if self.token_status != 200:
                return httpx2.Response(
                    self.token_status, json={"error": GOOGLE_ERROR_TEXT}
                )
            return httpx2.Response(
                200,
                json={
                    "access_token": "access-1",
                    "expires_in": 3599,
                    "scope": GMAIL_SEND_SCOPE,
                    "token_type": "Bearer",
                },
            )
        if self.send_status != 200:
            return httpx2.Response(
                self.send_status, json={"error": {"message": GOOGLE_ERROR_TEXT}}
            )
        return httpx2.Response(200, json={"id": "sent-1", "labelIds": ["SENT"]})

    @property
    def sends(self) -> list[httpx2.Request]:
        return [r for r in self.requests if str(r.url) == SEND_URL]


def sender(handler: Handler) -> GmailSender:
    creds = GmailCredentials(
        client_id="id", client_secret=FAKE_SECRET, refresh_token=FAKE_SEND_REFRESH
    )
    return GmailSender(creds, MAILROOM, httpx2.MockTransport(handler))


def sent_message(google: FakeGoogle) -> EmailMessage:
    (request,) = google.sends
    raw = json.loads(request.content)["raw"]
    parsed = email.message_from_bytes(
        base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)), policy=policy.default
    )
    return parsed


def test_the_mail_is_plain_utf8_text_from_joboffer_at_the_mailbox(
    portal: BlockingPortal,
) -> None:
    google = FakeGoogle()

    portal.call(
        sender(google).send,
        OutgoingMail(
            to="candidate@example.com", subject="Тема", body="Привіт, світе\n"
        ),
    )

    message = sent_message(google)
    assert message["From"] == f"joboffer <{MAILROOM}>"
    assert message["To"] == "candidate@example.com"
    assert message.get_content_type() == "text/plain"
    assert message.get_content_charset() == "utf-8"
    assert message.get_content() == "Привіт, світе\n"
    assert not message.is_multipart()


def test_the_subject_is_utf8_and_transported_as_an_encoded_word(
    portal: BlockingPortal,
) -> None:
    google = FakeGoogle()

    portal.call(
        sender(google).send,
        OutgoingMail(
            to="a@example.com", subject="Код підтвердження joboffer", body="x"
        ),
    )

    message = sent_message(google)
    assert message["Subject"] == "Код підтвердження joboffer"
    subject_raw = next(v for k, v in message.raw_items() if k == "Subject")
    assert subject_raw.startswith("=?utf-8?")


def test_the_request_uses_the_send_only_refresh_token_and_a_bearer_access_token(
    portal: BlockingPortal,
) -> None:
    google = FakeGoogle()

    portal.call(
        sender(google).send, OutgoingMail(to="a@example.com", subject="s", body="b")
    )

    token_request, send_request = google.requests
    assert str(token_request.url) == OAUTH_URL
    assert f"refresh_token={FAKE_SEND_REFRESH}" in token_request.content.decode()
    assert str(send_request.url) == SEND_URL
    assert send_request.method == "POST"
    assert send_request.headers["Authorization"] == "Bearer access-1"


def test_a_recipient_with_header_injection_is_refused_before_any_request(
    portal: BlockingPortal,
) -> None:
    google = FakeGoogle()

    with pytest.raises(MailUnavailable):
        portal.call(
            sender(google).send,
            OutgoingMail(
                to="a@example.com\r\nBcc: x@example.com", subject="s", body="b"
            ),
        )

    assert google.requests == []


@pytest.mark.parametrize(
    ("send_status", "token_status"), [(500, 200), (403, 200), (200, 400), (200, 401)]
)
def test_a_google_failure_is_mail_unavailable_without_the_google_text(
    portal: BlockingPortal, send_status: int, token_status: int
) -> None:
    google = FakeGoogle(send_status=send_status, token_status=token_status)

    with pytest.raises(MailUnavailable) as raised:
        portal.call(
            sender(google).send, OutgoingMail(to="a@example.com", subject="s", body="b")
        )

    assert GOOGLE_ERROR_TEXT not in str(raised.value)
    assert GOOGLE_ERROR_TEXT not in repr(raised.value)
    assert raised.value.__cause__ is None
    assert FAKE_SEND_REFRESH not in str(raised.value)


def test_a_network_failure_is_mail_unavailable(portal: BlockingPortal) -> None:
    def broken(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused")

    with pytest.raises(MailUnavailable):
        portal.call(
            sender(broken).send, OutgoingMail(to="a@example.com", subject="s", body="b")
        )


def use_cases(google: FakeGoogle, store: SendStore, limit: int) -> OutgoingMailUseCases:
    return OutgoingMailUseCases(
        lambda: InMemorySendUnitOfWork(store),
        FakeClock(),
        OutgoingMailServices(
            sender=sender(google),
            templates=FileTemplates.load(TEMPLATES),
            audit=FakeAudit(),
            daily_limit=limit,
        ),
    )


def test_the_real_signup_mail_has_the_code_and_no_links(portal: BlockingPortal) -> None:
    google = FakeGoogle()

    portal.call(
        use_cases(google, SendStore(), 50).send_signup_code, "a@example.com", "483920"
    )

    message = sent_message(google)
    body = message.get_content()
    assert "483920" in body
    assert "$" not in body
    for marker in ("http", "://", "www.", "<a ", "href"):
        assert marker not in body.lower()
        assert marker not in str(message["Subject"]).lower()
    assert str(message["Subject"]).strip() != ""


def test_over_the_daily_limit_no_request_reaches_google(portal: BlockingPortal) -> None:
    google = FakeGoogle()
    cases = use_cases(google, SendStore(), 2)
    for _ in range(2):
        portal.call(cases.send_signup_code, "a@example.com", "111111")
    requests_before = len(google.requests)

    with pytest.raises(MailQuotaExceeded):
        portal.call(cases.send_signup_code, "a@example.com", "222222")

    assert len(google.requests) == requests_before
    assert len(google.sends) == 2
