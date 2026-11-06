"""Розбір листа (raw RFC 822) у `IncomingMail`: заголовки, текст (text/plain, інакше HTML →
текст) і опис вкладень без вмісту. Лист може прислати будь-хто: збій розбору поля не зупиняє
синк — він іде в `parse_error`, решта листа зберігається."""

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime

from domain.mail.mail import Attachment, IncomingMail, clip_text
from domain.mail.sender_auth import (
    ARC_AUTHENTICATION_RESULTS,
    ARC_SEAL,
    AUTHENTICATION_RESULTS,
)
from domain.shared.text import html_to_text, one_line, tidy_lines

# Заголовки автентифікації: лише витягуються, довіру до них визначає домен.
AUTH_HEADERS = frozenset({AUTHENTICATION_RESULTS, ARC_AUTHENTICATION_RESULTS, ARC_SEAL})


def parse_message(
    raw: bytes, *, message_id: str, received_at: datetime
) -> IncomingMail:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    errors: list[str] = []
    mail = IncomingMail(id=message_id, received_at=received_at)
    try:
        mail = _with_headers(mail, message)
    except Exception as exc:  # лист від будь-кого: див. докстрінг модуля
        errors.append(f"заголовки: {type(exc).__name__}")
    try:
        text, text_error = _text(message)
    except Exception as exc:
        text, text_error = "", f"текст: {type(exc).__name__}"
    if text_error:
        errors.append(text_error)
    try:
        attachments = tuple(_attachments(message))
    except Exception as exc:
        errors.append(f"вкладення: {type(exc).__name__}")
        attachments = ()
    return replace(
        mail,
        text=clip_text(text),
        attachments=attachments,
        parse_error="; ".join(errors),
    )


def _with_headers(mail: IncomingMail, message: EmailMessage) -> IncomingMail:
    sender = _addresses(message, "From")
    return replace(
        mail,
        message_id=_header(message, "Message-ID"),
        in_reply_to=next(iter(_header(message, "In-Reply-To").split()), ""),
        references=tuple(_header(message, "References").split()),
        from_address=sender[0][1] if sender else "",
        from_name=sender[0][0] if sender else "",
        to=tuple(address for _, address in _addresses(message, "To")),
        delivered_to=tuple(
            address for _, address in _addresses(message, "Delivered-To")
        ),
        subject=one_line(_header(message, "Subject")),
        sent_at=_date(_header(message, "Date")),
        auth_headers=tuple(
            (name.lower(), " ".join(str(value).split()))
            for name, value in message.items()
            if name.lower() in AUTH_HEADERS
        ),
    )


def _header(message: EmailMessage, name: str) -> str:
    return str(message.get(name, "")).strip()


def _addresses(message: EmailMessage, name: str) -> list[tuple[str, str]]:
    """(ім'я, адреса нижнім регістром) з усіх заголовків name; без адреси — пропускаються."""
    values = [str(value) for value in message.get_all(name, [])]
    return [
        (one_line(display), address.lower())
        for display, address in getaddresses(values)
        if address
    ]


def _date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        sent_at = parsedate_to_datetime(value)
    except TypeError, ValueError:
        return None
    # «-0000» — пояс невідомий: вважаємо UTC.
    return sent_at if sent_at.tzinfo else sent_at.replace(tzinfo=UTC)


def _text(message: EmailMessage) -> tuple[str, str]:
    """Текст листа і помилка розбору (порожня — без помилок)."""
    body = message.get_body(preferencelist=("plain", "html"))
    if body is None:
        return "", ""
    error = ""
    try:
        content = body.get_content()
    except LookupError:  # невідоме кодування — читаємо як UTF-8 із заміною
        payload = body.get_payload(decode=True)
        content = payload.decode(errors="replace") if isinstance(payload, bytes) else ""
        error = f"кодування {body.get_content_charset()}"
    if body.get_content_subtype() == "html":
        content = html_to_text(content)
    return tidy_lines(content.splitlines()), error


def _attachments(message: EmailMessage) -> Iterable[Attachment]:
    for part in message.iter_attachments():
        payload = part.get_payload(decode=True)
        yield Attachment(
            filename=one_line(part.get_filename() or ""),
            content_type=part.get_content_type(),
            size=len(payload) if isinstance(payload, bytes) else 0,
        )
