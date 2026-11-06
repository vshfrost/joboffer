"""Розбір листа Gmail (raw RFC 822) у IncomingMail."""

import base64
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from domain.mail.mail import (
    MAX_TEXT_BYTES,
    Attachment,
    ForwardingRequest,
    IncomingMail,
    forwarding_request,
)
from infrastructure.gmail import parse
from infrastructure.gmail.parse import parse_message

FIXTURES = Path(__file__).parent / "gmail_fixtures"
RECEIVED_AT = datetime(2026, 10, 13, 8, 16, tzinfo=UTC)


def parsed(raw: bytes) -> IncomingMail:
    return parse_message(raw, message_id="m1", received_at=RECEIVED_AT)


def test_forwarded_reply_keeps_headers_text_and_attachment_metadata() -> None:
    mail = parsed((FIXTURES / "reply.eml").read_bytes())

    assert mail.id == "m1"
    assert mail.received_at == RECEIVED_AT
    assert mail.message_id == "<reply-1@acme.example>"
    assert mail.in_reply_to == "<application-1@example.com>"
    assert mail.references == ("<thread-0@acme.example>", "<application-1@example.com>")
    assert mail.from_address == "talent@acme.example"
    assert mail.from_name == "María López"
    assert mail.to == ("taras@example.com",)
    # Пересилання додає свій Delivered-To згори: обидва зберігаються в порядку заголовків.
    assert mail.delivered_to == (
        "mailroom+abcdefghijkl@example.com",
        "taras@example.com",
    )
    assert mail.subject == "Re: Senior Backend Engineer — next steps"
    assert mail.sent_at == datetime(
        2026, 10, 13, 10, 15, tzinfo=timezone(timedelta(hours=2))
    )
    # text/plain має перевагу над HTML; порожні рядки стиснуто до одного, пробіли — теж.
    assert mail.text == (
        "Hi Taras,\n\nThanks for applying. Could we schedule a call this week?\n\n"
        "Best,\nMaría"
    )
    assert mail.attachments == (
        Attachment(
            "assignment.pdf",
            "application/pdf",
            len(base64.b64decode("JVBERi0xLjQKJcfsj6IK")),
        ),
    )
    assert mail.parse_error == ""


def test_authentication_headers_are_taken_top_down_without_interpretation() -> None:
    mail = parsed((FIXTURES / "forwarded_company.eml").read_bytes())

    assert [(name, value.split(";")[0]) for name, value in mail.auth_headers] == [
        ("arc-seal", "i=5"),
        ("arc-authentication-results", "i=5"),
        ("authentication-results", "mx.google.com"),
        # Нижній Authentication-Results (від mx.cloudflare.net) теж віддається — зверху вниз.
        ("authentication-results", "mx.cloudflare.net"),
        ("arc-seal", "i=4"),
        ("arc-authentication-results", "i=4"),
        ("arc-seal", "i=3"),
        ("arc-authentication-results", "i=3"),
        ("arc-seal", "i=2"),
        ("arc-authentication-results", "i=2"),
        ("arc-seal", "i=1"),
        ("arc-authentication-results", "i=1"),
    ]
    assert all(
        "\n" not in value and "  " not in value for _, value in mail.auth_headers
    )
    cloudflare = dict(mail.auth_headers[9:10])["arc-authentication-results"]
    assert cloudflare.startswith("i=2; mx.cloudflare.net; dkim=pass header.d=gmail.com")
    assert "d=cloudflare-email.net" in mail.auth_headers[8][1]


def test_mail_without_authentication_headers_has_none() -> None:
    assert parsed((FIXTURES / "reply.eml").read_bytes()).auth_headers == ()


def test_html_only_mail_becomes_text_without_markup_scripts_or_styles() -> None:
    mail = parsed((FIXTURES / "alert.eml").read_bytes())

    assert mail.text == (
        "New jobs\n\nSenior Backend at Acme\nValencia\n\nFintech & payments"
    )
    assert mail.from_name == "Jobs"
    # «-0000» — пояс невідомий: UTC.
    assert mail.sent_at == datetime(2026, 10, 14, 8, 0, tzinfo=UTC)
    assert mail.attachments == ()


def test_unknown_charset_is_read_as_utf8_and_reported() -> None:
    mail = parsed(
        b'Content-Type: text/plain; charset="x-klingon"\r\n\r\nHello\xff there\r\n'
    )

    assert mail.text == "Hello� there"
    assert mail.parse_error == "кодування x-klingon"


def test_mail_without_headers_or_body_gives_empty_fields() -> None:
    mail = parsed(b"\r\n")

    assert mail.message_id == mail.in_reply_to == mail.from_address == ""
    assert mail.references == mail.to == mail.delivered_to == ()
    assert mail.sent_at is None
    assert mail.text == ""
    assert mail.parse_error == ""


def test_attachments_only_mail_has_no_text() -> None:
    raw = (
        b'Content-Type: multipart/mixed; boundary="b"\r\n\r\n'
        b"--b\r\nContent-Type: application/octet-stream\r\n"
        b"Content-Disposition: attachment\r\n\r\ndata\r\n"
        b"--b\r\nContent-Type: message/rfc822\r\n"
        b'Content-Disposition: attachment; filename="fwd.eml"\r\n\r\n'
        b"Subject: inner\r\n\r\nbody\r\n--b--\r\n"
    )

    mail = parsed(raw)

    assert mail.text == ""
    assert mail.attachments == (
        Attachment("", "application/octet-stream", 4),
        Attachment("fwd.eml", "message/rfc822", 0),
    )


def test_unparsable_date_is_empty() -> None:
    assert parsed(b"Date: not a date\r\n\r\nhi\r\n").sent_at is None


def test_long_text_is_clipped_to_the_limit() -> None:
    mail = parsed(b"Content-Type: text/plain\r\n\r\n" + b"a" * (MAX_TEXT_BYTES + 10))

    assert len(mail.text.encode()) == MAX_TEXT_BYTES


@pytest.mark.parametrize(
    ("part", "error"),
    [
        ("_with_headers", "заголовки: RuntimeError"),
        ("_text", "текст: RuntimeError"),
        ("_attachments", "вкладення: RuntimeError"),
    ],
)
def test_failed_part_is_reported_and_the_rest_is_kept(
    monkeypatch: pytest.MonkeyPatch, part: str, error: str
) -> None:
    def broken(*args: object) -> None:
        raise RuntimeError

    monkeypatch.setattr(parse, part, broken)

    mail = parsed((FIXTURES / "reply.eml").read_bytes())

    assert mail.parse_error == error
    assert mail.id == "m1"
    assert (mail.subject != "") == (part != "_with_headers")
    assert (mail.text != "") == (part != "_text")
    assert (mail.attachments != ()) == (part != "_attachments")


def test_real_gmail_confirmation_gives_the_initiator_and_an_empty_code() -> None:
    """Справжній лист Gmail (2026-10, знеособлений): коду нема ні в темі, ні в тексті — лише
    посилання. Запит усе одно впізнається: з ініціатором і порожнім кодом."""
    mail = parsed((FIXTURES / "forwarding_confirmation.eml").read_bytes())

    found = forwarding_request(
        mail.subject, mail.text, RECEIVED_AT, "mailroom+abcdefghijkl@example.com"
    )

    assert found == ForwardingRequest("", "taras@example.com", RECEIVED_AT)


def test_forwarding_code_in_the_subject_of_a_parsed_letter_is_extracted() -> None:
    raw = (
        b"From: Gmail Team <forwarding-noreply@google.com>\r\n"
        b"Subject: (#418306552) Gmail Forwarding Confirmation - Receive Mail from "
        b"taras@example.com\r\n\r\ntaras@example.com has requested to forward mail.\r\n"
    )
    mail = parsed(raw)

    found = forwarding_request(mail.subject, mail.text, RECEIVED_AT, "own@example.com")

    assert found == ForwardingRequest("418306552", "taras@example.com", RECEIVED_AT)
