"""Пошта (домен): обрізання тексту, особиста адреса й tag, вид листа за відправником, код
пересилання Gmail, запис про відкинутий лист."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from domain.mail.mail import (
    MAX_DROPPED_SUBJECT,
    MAX_TEXT_BYTES,
    TAG_ALPHABET,
    TAG_LENGTH,
    DroppedRecord,
    DropReason,
    ForwardingRequest,
    IncomingMail,
    MailCategory,
    clip_text,
    forwarding_request,
    mail_category,
    mail_tag,
    personal_address,
)
from domain.mail.sender_auth import SenderAuth


def test_short_text_is_kept() -> None:
    assert clip_text("Hi Taras") == "Hi Taras"


def test_long_text_is_clipped_without_breaking_a_character() -> None:
    text = "a" + "ї" * MAX_TEXT_BYTES  # «ї» — два байти в UTF-8

    clipped = clip_text(text)

    assert len(clipped.encode()) == MAX_TEXT_BYTES - 1
    assert text.startswith(clipped)


MAILBOX = "Mailroom@Example.com"


def test_personal_address_is_mailbox_with_tag() -> None:
    assert (
        personal_address(MAILBOX, "abcdefghijkl") == "mailroom+abcdefghijkl@example.com"
    )


@pytest.mark.parametrize(
    ("delivered_to", "tag"),
    [
        (("mailroom+abcdefghijkl@example.com",), "abcdefghijkl"),
        # Верхній Delivered-To — останнє доставлення; адреса користувача нижче не заважає.
        (("mailroom+abcdefghijkl@example.com", "taras@example.com"), "abcdefghijkl"),
        (("taras@example.com", "mailroom+zyxw23456722@example.com"), "zyxw23456722"),
        (("mailroom@example.com",), None),
        (("mailroom+@example.com",), None),
        (("other+abcdefghijkl@example.com",), None),
        (("mailroom+abcdefghijkl@other.example",), None),
        (("mailroom+abcdefghijk@example.com",), None),  # 11 символів
        (("mailroom+abcdefghijklm@example.com",), None),  # 13
        (("mailroom+abcdefghijk1@example.com",), None),  # 1 — не з алфавіту
        ((), None),
    ],
)
def test_mail_tag_comes_only_from_personal_address(
    delivered_to: tuple[str, ...], tag: str | None
) -> None:
    assert mail_tag(delivered_to, MAILBOX) == tag


def test_tag_alphabet_and_length() -> None:
    assert len(TAG_ALPHABET) == 32
    assert TAG_LENGTH == 12


@pytest.mark.parametrize(
    ("sender", "category"),
    [
        ("forwarding-noreply@google.com", MailCategory.FORWARDING_CONFIRMATION),
        ("jobalerts-noreply@linkedin.com", MailCategory.LINKEDIN_ALERT),
        ("jobs-noreply@linkedin.com", MailCategory.LINKEDIN_APPLICATION),
        ("messages-noreply@linkedin.com", MailCategory.LINKEDIN_MESSAGE),
        ("inmail-hit-reply@linkedin.com", MailCategory.LINKEDIN_MESSAGE),
        ("news@linkedin.com", MailCategory.OTHER),
        ("security@e.linkedin.com", MailCategory.OTHER),
        ("", MailCategory.OTHER),
        ("talent@acme.example", MailCategory.COMPANY),
        ("no-reply@greenhouse.io", MailCategory.COMPANY),
    ],
)
def test_mail_category_by_sender(sender: str, category: MailCategory) -> None:
    assert mail_category(sender, SenderAuth.VERIFIED) == category


@pytest.mark.parametrize(
    ("sender", "auth", "category"),
    [
        # Підроблений відправник — suspicious, якою б не була адреса.
        ("talent@acme.example", SenderAuth.FAILED, MailCategory.SUSPICIOUS),
        ("forwarding-noreply@google.com", SenderAuth.FAILED, MailCategory.SUSPICIOUS),
        ("jobalerts-noreply@linkedin.com", SenderAuth.FAILED, MailCategory.SUSPICIOUS),
        ("", SenderAuth.FAILED, MailCategory.SUSPICIOUS),
        # Непідтверджений: категорія та сама, крім підтвердження пересилання.
        ("talent@acme.example", SenderAuth.UNKNOWN, MailCategory.COMPANY),
        (
            "jobalerts-noreply@linkedin.com",
            SenderAuth.UNKNOWN,
            MailCategory.LINKEDIN_ALERT,
        ),
        ("forwarding-noreply@google.com", SenderAuth.UNKNOWN, MailCategory.OTHER),
    ],
)
def test_mail_category_follows_sender_authenticity(
    sender: str, auth: SenderAuth, category: MailCategory
) -> None:
    assert mail_category(sender, auth) == category


RECEIVED = datetime(2026, 10, 14, tzinfo=UTC)
OWN = "mailroom+abcdefghijkl@example.com"


# Теми й тексти — як у листах Gmail про пересилання англійською, іспанською й українською.
@pytest.mark.parametrize(
    ("subject", "text"),
    [
        (
            "(#418306552) Gmail Forwarding Confirmation - Receive Mail from Taras@Example.com",
            f"taras@example.com has requested to automatically forward mail to {OWN}.",
        ),
        (
            "(#418306552) Confirmación de reenvío de Gmail: recibir correo de taras@example.com",
            f"taras@example.com ha solicitado reenviar automáticamente correo a {OWN}.",
        ),
        (
            "(#418306552) Підтвердження пересилання Gmail – отримувати пошту з адреси "
            "taras@example.com",
            f"taras@example.com надіслав запит на автоматичне пересилання пошти на {OWN}.",
        ),
        (
            "Gmail Forwarding Confirmation",
            f"To {OWN}: Confirmation code: 418306552 from taras@example.com",
        ),
        (
            "Confirmación de reenvío",
            "Código de confirmación: 418306552\ntaras@example.com",
        ),
        (
            "Підтвердження пересилання",
            f"{OWN}\nКод підтвердження: 418306552 · taras@example.com",
        ),
    ],
)
def test_forwarding_request_in_english_spanish_and_ukrainian(
    subject: str, text: str
) -> None:
    assert forwarding_request(subject, text, RECEIVED, OWN) == ForwardingRequest(
        "418306552", "taras@example.com", RECEIVED
    )


def test_forwarding_request_without_initiator_keeps_the_code() -> None:
    found = forwarding_request("(#418306552) x", f"to {OWN}", RECEIVED, OWN)

    assert found == ForwardingRequest("418306552", "", RECEIVED)


@pytest.mark.parametrize(
    ("subject", "text"),
    [("(#12) short", "no code here"), ("Re: interview", "Call me at 600123456")],
)
def test_mail_without_forwarding_code_gives_an_empty_code(
    subject: str, text: str
) -> None:
    assert forwarding_request(subject, text, RECEIVED, OWN) == ForwardingRequest(
        "", "", RECEIVED
    )


def letter(**fields: object) -> IncomingMail:
    base = IncomingMail(
        id="g1",
        received_at=RECEIVED,
        from_address="talent@acme.example",
        from_name="María",
        subject="Re: next steps",
        text="Could we schedule a call?",
    )
    return replace(base, **fields)  # type: ignore[arg-type]


def test_dropped_record_keeps_reason_date_sender_and_subject() -> None:
    record = DroppedRecord.of(letter(), DropReason.DAILY_LIMIT)

    assert record == DroppedRecord(
        "g1", DropReason.DAILY_LIMIT, RECEIVED, "talent@acme.example", "Re: next steps"
    )


def test_dropped_record_has_no_mail_text() -> None:
    record = DroppedRecord.of(letter(), DropReason.RETIRED_TAG)

    assert "Could we schedule" not in repr(record)
    assert not hasattr(record, "text")


@pytest.mark.parametrize(
    ("length", "kept"),
    [
        (MAX_DROPPED_SUBJECT - 1, MAX_DROPPED_SUBJECT - 1),
        (MAX_DROPPED_SUBJECT, 200),
        (MAX_DROPPED_SUBJECT + 1, 200),
        (5000, 200),
    ],
)
def test_dropped_subject_is_cut_to_200_characters(length: int, kept: int) -> None:
    record = DroppedRecord.of(letter(subject="я" * length), DropReason.DAILY_LIMIT)

    assert record.subject == "я" * kept
    assert MAX_DROPPED_SUBJECT == 200
