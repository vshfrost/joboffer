"""Ручне пересилання: блок пересланого листа в тексті (Gmail EN / ES / UK, Apple Mail).
Це пересилання, лише якщо From = email із профілю власника і DMARC пройдено."""

import pytest

from domain.mail.forwarded import ForwardedMail, forwarded_block, manual_forward
from domain.mail.sender_auth import SenderAuth

OWNER = "owner@owner.example"
VERIFIED = SenderAuth.VERIFIED
ANA = "ana.recruiter@acme.example"

GMAIL_EN = f"""\
---------- Forwarded message ---------
From: Ana Recruiter <{ANA}>
Date: Mon, Oct 19, 2026 at 10:15 AM
Subject: Message replied: Senior Backend Developer | ACME
To: Owner <{OWNER}>


Hola, fyi"""
GMAIL_ES = f"""\
---------- Mensaje reenviado ---------
De: Ana Recruiter <{ANA}>
Fecha: lun, 19 oct 2026 a las 10:15
Asunto: Mensaje respondido: Senior Backend Developer | ACME
Para: Owner <{OWNER}>


Hola, fyi"""
GMAIL_UK = f"""\
---------- Переслане повідомлення ---------
Від: Ana Recruiter <{ANA}>
Дата: пн, 19 жовт. 2026 р. о 10:15
Тема: Відповідь: Senior Backend Developer | ACME
Кому: Owner <{OWNER}>


Привіт"""
APPLE_MAIL = f"""\
Begin forwarded message:

From: Ana Recruiter <{ANA}>
Subject: Message replied: Senior Backend Developer | ACME
Date: 19 October 2026 at 10:15:00 CEST
To: Owner <{OWNER}>

Hola, fyi"""
APPLE_MAIL_COMPACT = APPLE_MAIL.replace(
    "forwarded message:\n\n", "forwarded message:\n"
)


def forwarded(subject: str) -> ForwardedMail:
    return ForwardedMail(ANA, "Ana Recruiter", subject)


@pytest.mark.parametrize(
    ("text", "subject"),
    [
        (GMAIL_EN, "Message replied: Senior Backend Developer | ACME"),
        (GMAIL_ES, "Mensaje respondido: Senior Backend Developer | ACME"),
        (GMAIL_UK, "Відповідь: Senior Backend Developer | ACME"),
        (APPLE_MAIL, "Message replied: Senior Backend Developer | ACME"),
        (APPLE_MAIL_COMPACT, "Message replied: Senior Backend Developer | ACME"),
    ],
    ids=["gmail-en", "gmail-es", "gmail-uk", "apple-mail", "apple-mail-compact"],
)
def test_the_forwarded_block_gives_the_original_sender_and_subject(
    text: str, subject: str
) -> None:
    assert forwarded_block(text) == forwarded(subject)


def test_a_mail_from_the_profile_email_with_a_verified_sender_is_a_manual_forward() -> (
    None
):
    found = manual_forward(OWNER, OWNER, VERIFIED, GMAIL_EN)

    assert found == forwarded("Message replied: Senior Backend Developer | ACME")


def test_the_owner_email_is_compared_case_insensitively() -> None:
    found = manual_forward(" Owner@Owner.EXAMPLE ", OWNER, VERIFIED, GMAIL_EN)

    assert found is not None
    assert found.from_address == ANA


@pytest.mark.parametrize("auth", [SenderAuth.UNKNOWN, SenderAuth.FAILED])
def test_a_forged_mail_from_the_owner_is_not_trusted(auth: SenderAuth) -> None:
    assert manual_forward(OWNER, OWNER, auth, GMAIL_EN) is None


@pytest.mark.parametrize(
    ("owner", "sender"),
    [
        (OWNER, "someone@elsewhere.example"),
        ("", OWNER),
        ("other@owner.example", OWNER),
    ],
)
def test_only_a_mail_from_the_profile_email_is_a_manual_forward(
    owner: str, sender: str
) -> None:
    assert manual_forward(owner, sender, VERIFIED, GMAIL_EN) is None


def test_no_forwarded_block_is_not_a_manual_forward() -> None:
    assert manual_forward(OWNER, OWNER, VERIFIED, "Hola, fyi\n\nBye") is None
    assert forwarded_block("") is None


def test_the_top_block_wins_over_a_nested_forward() -> None:
    text = (
        "---------- Forwarded message ---------\n"
        f"From: Owner <{OWNER}>\nSubject: Fwd: Hello\n\n"
        "---------- Forwarded message ---------\n"
        f"From: Ana <{ANA}>\nSubject: Hello\n"
    )

    assert forwarded_block(text) == ForwardedMail(OWNER, "Owner", "Fwd: Hello")


def test_a_block_without_an_address_in_from_is_not_a_block() -> None:
    nameless = GMAIL_EN.replace(f"Ana Recruiter <{ANA}>", "Ana")
    no_from = GMAIL_EN.replace(f"From: Ana Recruiter <{ANA}>\n", "")
    # Рядок From після порожнього рядка — уже не заголовок блоку Gmail.
    late = f"---------- Forwarded message ---------\n\nFrom: {ANA}\n"

    assert forwarded_block(nameless) is None
    assert forwarded_block(no_from) is None
    assert forwarded_block(late) is None


def test_the_address_is_lowercased_and_the_name_and_subject_are_cleaned() -> None:
    zero_width, bidi = chr(0x200B), chr(0x202E)
    text = (
        "---------- Forwarded message ---------\n"
        f'From: "Ana{zero_width}   Recruiter" <Ana.Recruiter@ACME.example>\n'
        f"Subject:  Re:{bidi}  Offer \n"
        "not a header line\n"
        "From: second@acme.example\n"
        "Subject: second\n"
    )

    assert forwarded_block(text) == ForwardedMail(ANA, "Ana Recruiter", "Re: Offer")


def test_a_bare_address_has_no_name_and_a_missing_subject_is_empty() -> None:
    text = f"---------- Forwarded message ---------\nFrom: {ANA}\n"

    assert forwarded_block(text) == ForwardedMail(ANA, "", "")


def test_too_long_values_are_clipped_or_rejected() -> None:
    long_address = f"{'a' * 250}@acme.example"
    head = "---------- Forwarded message ---------\n"

    assert forwarded_block(f"{head}From: {long_address}\n") is None
    block = forwarded_block(f"{head}From: {'N' * 500} <a@acme.example>\n")
    assert block is not None
    assert len(block.from_name) == 200
    long_subject = forwarded_block(f"{head}From: {ANA}\nSubject: {'S' * 500}\n")
    assert long_subject is not None
    assert len(long_subject.subject) == 300
