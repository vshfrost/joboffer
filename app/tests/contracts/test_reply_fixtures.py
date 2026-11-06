"""Зіставлення й підказка типу на листах реального вигляду: фікстури `.eml` розібрані через
Gmail-парсер, як у синку (8 листів компаній і рекрутерів, знеособлені)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from domain.applications.application import ApplicationStatus, AtsPlatform
from domain.mail.forwarded import ForwardedMail, manual_forward
from domain.mail.replies import (
    AppliedJob,
    Confidence,
    MatchedBy,
    ReplyMail,
    ReplyMatch,
    ReplyType,
    match_reply,
    suggest_type,
)
from domain.mail.sender_auth import SenderAuth, sender_auth
from infrastructure.gmail.parse import parse_message

FIXTURES = Path(__file__).parent / "reply_fixtures"
NOW = datetime(2026, 10, 15, 14, tzinfo=UTC)
APPLIED = ApplicationStatus.APPLIED

ACME = AppliedJob(
    1, "Senior Backend Engineer", "Acme Inc.", APPLIED, AtsPlatform.GREENHOUSE
)
TIDEWELL = AppliedJob(
    2, "Backend Engineer, Payments", "Tidewell", APPLIED, AtsPlatform.LEVER
)
LARKSPUR = AppliedJob(
    3, "Senior Backend Engineer", "Larkspur", APPLIED, AtsPlatform.ASHBY
)
QUILLFORM = AppliedJob(
    4, "Backend Engineer", "Quillform S.L.", APPLIED, AtsPlatform.WORKABLE
)
REDCART = AppliedJob(
    5,
    "Senior Backend Engineer",
    "Redcart",
    APPLIED,
    company_domains=("redcart.example",),
)
MERIDIANBANK = AppliedJob(
    6,
    "Senior Backend Engineer (Payments)",
    "Meridianbank",
    APPLIED,
    None,
    ("meridianbank.example",),
)
BOARD = (ACME, TIDEWELL, LARKSPUR, QUILLFORM, REDCART, MERIDIANBANK)


def fixture(name: str) -> ReplyMail:
    raw = (FIXTURES / f"{name}.eml").read_bytes()
    mail = parse_message(raw, message_id=name, received_at=NOW)
    assert mail.parse_error == ""
    return ReplyMail(
        id=1,
        received_at=mail.received_at,
        message_id=mail.message_id,
        in_reply_to=mail.in_reply_to,
        references=mail.references,
        from_address=mail.from_address,
        from_name=mail.from_name,
        subject=mail.subject,
        text=mail.text,
    )


@pytest.mark.parametrize(
    ("name", "job", "confidence", "matched_by", "kind"),
    [
        (
            "greenhouse_confirmation_en",
            ACME,
            Confidence.HIGH,
            MatchedBy.ATS,
            ReplyType.AUTO_CONFIRMATION,
        ),
        (
            "lever_rejection_en",
            TIDEWELL,
            Confidence.HIGH,
            MatchedBy.ATS,
            ReplyType.REJECTION,
        ),
        (
            "ashby_invitation_en",
            LARKSPUR,
            Confidence.HIGH,
            MatchedBy.ATS,
            ReplyType.INVITATION,
        ),
        (
            "workable_rejection_es",
            QUILLFORM,
            Confidence.HIGH,
            MatchedBy.ATS,
            ReplyType.REJECTION,
        ),
        (
            "company_invitation_es",
            REDCART,
            Confidence.HIGH,
            MatchedBy.DOMAIN,
            ReplyType.INVITATION,
        ),
        (
            "company_assignment_en",
            MERIDIANBANK,
            Confidence.HIGH,
            MatchedBy.DOMAIN,
            ReplyType.ASSIGNMENT,
        ),
        ("unrelated_newsletter_en", None, None, None, ReplyType.OTHER),
    ],
)
def test_real_looking_replies_match_their_application_and_type(
    name: str,
    job: AppliedJob | None,
    confidence: Confidence | None,
    matched_by: MatchedBy | None,
    kind: ReplyType,
) -> None:
    mail = fixture(name)

    assert match_reply(mail, BOARD, None) == ReplyMatch(
        None if job is None else job.job_number, confidence, matched_by
    )
    assert suggest_type(mail.subject, mail.text) is kind


def test_a_thread_reply_from_a_personal_address_follows_the_thread() -> None:
    mail = fixture("thread_reply_en")

    assert mail.thread_ids == ("<ashby-invite-1@ashbyhq.com>",) * 2
    assert match_reply(mail, BOARD, LARKSPUR.job_number) == ReplyMatch(
        LARKSPUR.job_number, Confidence.HIGH, MatchedBy.THREAD
    )
    # Процитоване «Thanks for applying» не робить відповідь автопідтвердженням.
    assert suggest_type(mail.subject, mail.text) is ReplyType.OTHER


def test_a_real_gmail_forward_of_the_owner_gives_the_original_sender() -> None:
    raw = (FIXTURES / "manual_forward.eml").read_bytes()
    mail = parse_message(raw, message_id="m1", received_at=NOW)

    assert mail.from_address == "owner@owner.example"
    assert sender_auth(mail.auth_headers, mail.from_address) is SenderAuth.VERIFIED
    assert manual_forward(
        "owner@owner.example", mail.from_address, SenderAuth.VERIFIED, mail.text
    ) == ForwardedMail(
        "ana.recruiter@acme.example",
        "Ana Recruiter",
        "Message replied: Senior Backend Developer | ACME",
    )
