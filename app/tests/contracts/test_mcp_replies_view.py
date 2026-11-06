"""Вигляд відповіді для агента: час за Мадридом, текст до 4000 символів, enum-и, ручне пересилання."""

from datetime import UTC, datetime

import pytest

from application.contracts.mail import MailInboxData
from domain.applications.application import ApplicationStatus
from domain.mail.forwarded import ForwardedMail
from domain.mail.inbox import DroppedSummary, MailSummary
from domain.mail.mail import MailCategory
from domain.mail.replies import (
    REPLY_TEXT_LIMIT,
    Confidence,
    MatchedBy,
    Reply,
    ReplyJob,
    ReplyType,
)
from domain.mail.sender_auth import SenderAuth
from infrastructure.mcp.tools.mail import ForwardedView, mail_inbox_view
from infrastructure.mcp.tools.replies import ReplyJobView, reply_view

SUMMER = datetime(2026, 7, 1, 10, 5, tzinfo=UTC)
WINTER = datetime(2026, 1, 15, 10, 5, tzinfo=UTC)


def reply(
    text: str = "Hello", received_at: datetime = SUMMER, **fields: object
) -> Reply:
    summary = MailSummary(
        id=7,
        from_address="hr@acme.example",
        from_name="María",
        subject="Next steps",
        category=MailCategory.COMPANY,
        received_at=received_at,
        sender_auth=SenderAuth.VERIFIED,
    )
    defaults: dict[str, object] = {
        "id": 3,
        "mail": summary,
        "text": text,
        "job": None,
        "confidence": None,
        "matched_by": None,
        "suggested_type": ReplyType.OTHER,
    }
    return Reply(**(defaults | fields))  # type: ignore[arg-type]


def test_the_mail_fields_are_mapped_and_third_party_text_is_named_untrusted() -> None:
    view = reply_view(reply())

    assert view.reply_id == 3
    assert view.from_address == "hr@acme.example"
    assert view.untrusted_from_name == "María"
    assert view.untrusted_subject == "Next steps"
    assert view.untrusted_text == "Hello"
    assert view.sender_auth == "verified"


def test_received_is_in_madrid_time_with_summer_and_winter_offsets() -> None:
    assert reply_view(reply(received_at=SUMMER)).received == "2026-07-01 12:05"
    assert reply_view(reply(received_at=WINTER)).received == "2026-01-15 11:05"


def test_a_text_of_exactly_the_limit_is_not_clipped() -> None:
    view = reply_view(reply("x" * REPLY_TEXT_LIMIT))

    assert (len(view.untrusted_text), view.text_clipped) == (4000, False)


def test_a_longer_text_is_clipped_to_4000_characters_and_flagged() -> None:
    view = reply_view(reply("x" * (REPLY_TEXT_LIMIT + 1)))

    assert (len(view.untrusted_text), view.text_clipped) == (4000, True)


def test_the_match_and_the_review_are_mapped_to_plain_values() -> None:
    found = reply(
        job=ReplyJob(2, "Backend", "Acme", ApplicationStatus.REPLIED),
        confidence=Confidence.MEDIUM,
        matched_by=MatchedBy.DOMAIN,
        suggested_type=ReplyType.INVITATION,
        type=ReplyType.REJECTION,
    )

    view = reply_view(found)

    assert view.job == ReplyJobView(
        job_id=2, title="Backend", company="Acme", status="replied"
    )
    assert (view.confidence, view.matched_by) == ("medium", "domain")
    assert (view.suggested_type, view.type) == ("invitation", "rejection")


def test_a_reply_without_a_match_or_review_has_nulls() -> None:
    view = reply_view(reply())

    assert (view.job, view.confidence, view.matched_by, view.type) == (
        None,
        None,
        None,
        None,
    )
    assert view.manual_forward is None
    assert view.suggested_type == "other"


def test_a_job_without_an_application_has_no_status() -> None:
    view = reply_view(reply(job=ReplyJob(2, None, None, None)))

    assert view.job == ReplyJobView(job_id=2, title=None, company=None, status=None)


def test_a_manual_forward_gives_the_block_sender_and_subject() -> None:
    forwarded = ForwardedMail("ana@acme.example", "Ana Recruiter", "Hello")

    view = reply_view(reply(forwarded=forwarded))

    assert view.manual_forward == ForwardedView(
        untrusted_from_address="ana@acme.example",
        untrusted_from_name="Ana Recruiter",
        untrusted_subject="Hello",
    )


@pytest.mark.parametrize("known", [True, False])
def test_the_mail_inbox_view_fills_manual_forward_for_forwarded_mail(
    known: bool,
) -> None:
    summary = MailSummary(
        id=5,
        from_address="owner@owner.example",
        from_name="Owner",
        subject="Fwd: Hello",
        category=MailCategory.COMPANY,
        received_at=SUMMER,
        sender_auth=SenderAuth.VERIFIED,
    )
    forwarded = {5: ForwardedMail("ana@acme.example", "Ana Recruiter", "Hello")}
    inbox = MailInboxData(
        address="mailroom+aaaaaaaaaaaa@example.com",
        forwarding=None,
        recent=(summary,),
        synced_at=None,
        sync_failed=False,
        limit_drops=DroppedSummary(),
        old_address_drops=DroppedSummary(),
        suspicious=DroppedSummary(),
        forwarded=forwarded if known else {},
    )

    mails = mail_inbox_view(inbox, "http://web").recent
    assert len(mails) == 1
    mail = mails[0]

    assert mail.manual_forward == (
        ForwardedView(
            untrusted_from_address="ana@acme.example",
            untrusted_from_name="Ana Recruiter",
            untrusted_subject="Hello",
        )
        if known
        else None
    )
