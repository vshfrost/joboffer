"""PostgresJobReplies на справжній базі: листи компаній без зіставлення, тред, подані вакансії, список,
розбір, ізоляція користувачів, схема для ETL, синк із зіставленням."""

from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from application.mail.sync import MailSyncUseCases
from domain.applications.application import (
    ApplicationStatus,
    AtsPlatform,
)
from domain.identity.ids import UserId
from domain.mail.mail import IncomingMail, MailCategory, personal_address
from domain.mail.replies import (
    AppliedJob,
    Confidence,
    MatchedBy,
    Reply,
    ReplyJob,
    ReplyMail,
    ReplyMatch,
    ReplyType,
)
from domain.mail.sender_auth import SenderAuth
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from infrastructure.system import RandomIds
from tests.integration.test_applications_repository import _move, _save, details
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, _add, posting
from tests.integration.test_mail_repository import (
    MAILBOX,
    VERIFIED,
    _clean_sync_state,
    mail,
    rows,
    uow,
)
from tests.support.clock import FakeClock
from tests.support.mail import FakeMailbox, auth_headers

__all__ = ["_clean_sync_state", "uow"]

S = ApplicationStatus
LATER = NOW + timedelta(days=3)

# Усі поля таблиці `job_replies` v1 (крім ключів): ETL у B12 переносить їх без втрат.
V1_REPLY_COLUMNS = {
    "confidence",
    "matched_by",
    "suggested_type",
    "type",
    "reviewed_at",
    "created_at",
}


@pytest.fixture(autouse=True)
def _first_ids(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    """Листи й відповіді нумеруються з 1 у кожному тесті (номер листа — id у «Вхідних»)."""

    async def reset() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE mail_messages RESTART IDENTITY CASCADE"))

    portal.call(reset)


async def store_mail(
    factory: UnitOfWorkFactory,
    user_id: UserId,
    gmail_id: str,
    hours_ago: int = 1,
    category: MailCategory = MailCategory.COMPANY,
) -> None:
    async with factory() as tx:
        await tx.mail_messages.add(
            user_id, mail(gmail_id, hours_ago=hours_ago), category, VERIFIED
        )
        await tx.commit()


async def add_reply(
    factory: UnitOfWorkFactory,
    user_id: UserId,
    mail_id: int,
    job: int | None,
    suggested: ReplyType = ReplyType.OTHER,
) -> None:
    match = (
        ReplyMatch()
        if job is None
        else ReplyMatch(job, Confidence.HIGH, MatchedBy.DOMAIN)
    )
    async with factory() as tx:
        await tx.job_replies.add(user_id, mail_id, match, suggested)
        await tx.commit()


async def pending(factory: UnitOfWorkFactory) -> list[tuple[UserId, ReplyMail]]:
    async with factory() as tx:
        return await tx.job_replies.pending()


async def listed(
    factory: UnitOfWorkFactory,
    user_id: UserId,
    reviewed: bool = False,
    limit: int = 10,
) -> list[Reply]:
    async with factory() as tx:
        return await tx.job_replies.list(user_id, reviewed=reviewed, limit=limit)


def test_pending_are_company_mails_without_a_reply_of_all_users_oldest_first(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(store_mail, uow, ALICE, "g1", 1)
    portal.call(store_mail, uow, BOB, "g2", 3)
    portal.call(store_mail, uow, ALICE, "g3", 2, MailCategory.OTHER)
    portal.call(store_mail, uow, ALICE, "g4", 2)
    portal.call(add_reply, uow, ALICE, 1, None)

    found = portal.call(pending, uow)

    assert [(owner, item.message_id) for owner, item in found] == [
        (BOB, "<g2@acme.example>"),
        (ALICE, "<g4@acme.example>"),
    ]
    _, first = found[0]
    assert first.from_address == "talent@acme.example"
    assert first.from_name == "María"
    assert first.text == "Could we schedule a call?"
    assert first.sender_auth is VERIFIED
    assert first.in_reply_to == "<application@example.com>"
    assert first.references == ("<thread@acme.example>", "<application@example.com>")


def test_a_mail_gets_one_reply_even_when_added_twice(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    portal.call(store_mail, uow, ALICE, "g1")
    portal.call(add_reply, uow, ALICE, 1, None, ReplyType.REJECTION)
    portal.call(add_reply, uow, ALICE, 1, None, ReplyType.OTHER)

    assert rows(portal, engine, "SELECT suggested_type FROM job_replies") == [
        ("rejection",)
    ]


async def _seed_jobs(factory: UnitOfWorkFactory) -> None:
    """Alice: вакансії 1 (Acme, domain, подана 2026-01-01), 2 (Tidewell, подана 2026-01-05), 3 (без подачі).
    Bob: вакансія 1 (Acme)."""
    await _add(factory, ALICE, posting("one", title="Backend", company="Acme"))
    await _add(factory, ALICE, posting("two", title="Data", company="Tidewell"))
    await _add(factory, ALICE, posting("three", title="Ops", company="Cobalt"))
    await _add(factory, BOB, posting("bob", title="Backend", company="Acme"))
    await _save(
        factory,
        ALICE,
        1,
        details(
            ats=AtsPlatform.GREENHOUSE,
            company_domains=("acme.com",),
            company_emails=("hr@acme.com",),
        ),
    )
    await _save(factory, ALICE, 2, details(applied_on=date(2026, 1, 5)))
    await _save(factory, BOB, 1, details())


def test_applied_jobs_are_the_users_applications_with_titles_newest_first(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_jobs, uow)
    portal.call(_move, uow, ALICE, 1, S.REPLIED)

    async def run() -> tuple[list[AppliedJob], list[AppliedJob]]:
        async with uow() as tx:
            return await tx.job_replies.applied(ALICE), await tx.job_replies.applied(
                BOB
            )

    alice, bob = portal.call(run)

    assert alice == [
        AppliedJob(2, "Data", "Tidewell", S.APPLIED),
        AppliedJob(
            1,
            "Backend",
            "Acme",
            S.REPLIED,
            AtsPlatform.GREENHOUSE,
            ("acme.com",),
            ("hr@acme.com",),
        ),
    ]
    assert bob == [AppliedJob(1, "Backend", "Acme", S.APPLIED)]


def test_thread_job_is_the_job_of_the_users_latest_matched_reply_with_that_message_id(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_jobs, uow)
    portal.call(store_mail, uow, ALICE, "g1", 3)
    portal.call(store_mail, uow, ALICE, "g2", 2)
    portal.call(store_mail, uow, BOB, "g3", 1)
    portal.call(add_reply, uow, ALICE, 1, 1)
    portal.call(add_reply, uow, ALICE, 2, None)
    portal.call(add_reply, uow, BOB, 3, 1)

    async def run() -> tuple[int | None, ...]:
        async with uow() as tx:
            replies = tx.job_replies
            return (
                await replies.thread_job(ALICE, ["<g1@acme.example>"]),
                await replies.thread_job(ALICE, ["<g2@acme.example>"]),
                await replies.thread_job(ALICE, ["<g3@acme.example>"]),
                await replies.thread_job(
                    BOB, ["<g3@acme.example>", "<g1@acme.example>"]
                ),
                await replies.thread_job(ALICE, []),
            )

    # g2 — лист без вакансії; g3 — лист Bob (для Alice чужий).
    assert portal.call(run) == (1, None, None, 1, None)


def test_list_has_reviewed_or_not_newest_first_with_the_job_and_its_status(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_jobs, uow)
    portal.call(_move, uow, ALICE, 1, S.INTERVIEW)
    for number, (gmail_id, hours) in enumerate((("g1", 3), ("g2", 1), ("g3", 2)), 1):
        portal.call(store_mail, uow, ALICE, gmail_id, hours)
        portal.call(add_reply, uow, ALICE, number, 1 if gmail_id != "g3" else None)

    async def review() -> None:
        async with uow() as tx:
            await tx.job_replies.review(ALICE, 3, 2, ReplyType.OTHER, LATER)
            await tx.commit()

    portal.call(review)

    fresh = portal.call(listed, uow, ALICE)
    done = portal.call(listed, uow, ALICE, True)
    one = portal.call(listed, uow, ALICE, False, 1)

    assert [r.mail.subject for r in fresh] == ["Re: next steps"] * 2
    assert [r.id for r in fresh] == [2, 1]
    assert [r.id for r in done] == [3]
    assert [r.id for r in one] == [2]
    first = fresh[0]
    assert first.job == ReplyJob(1, "Backend", "Acme", S.INTERVIEW)
    assert (first.confidence, first.matched_by) == (Confidence.HIGH, MatchedBy.DOMAIN)
    assert first.suggested_type is ReplyType.OTHER
    assert first.type is None
    assert first.reviewed_at is None
    assert first.text == "Could we schedule a call?"
    assert first.mail.from_address == "talent@acme.example"
    assert first.mail.sender_auth is SenderAuth.VERIFIED
    assert first.forwarded is None


def test_a_reply_of_another_user_is_neither_listed_nor_found(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_jobs, uow)
    portal.call(store_mail, uow, ALICE, "g1")
    portal.call(add_reply, uow, ALICE, 1, 1)

    async def run() -> tuple[Reply | None, Reply | None]:
        async with uow() as tx:
            return await tx.job_replies.get(ALICE, 1), await tx.job_replies.get(BOB, 1)

    mine, theirs = portal.call(run)

    assert mine is not None
    assert theirs is None
    assert portal.call(listed, uow, BOB) == []


def test_review_saves_the_type_the_job_and_the_time_and_replaces_the_previous(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_jobs, uow)
    portal.call(store_mail, uow, ALICE, "g1")
    portal.call(add_reply, uow, ALICE, 1, 1)

    async def review(job: int | None, kind: ReplyType, at: datetime) -> Reply:
        async with uow() as tx:
            done = await tx.job_replies.review(ALICE, 1, job, kind, at)
            await tx.commit()
            return done

    first = portal.call(review, 2, ReplyType.REJECTION, LATER)
    again = portal.call(review, None, ReplyType.INVITATION, LATER + timedelta(hours=1))

    assert first.type is ReplyType.REJECTION
    assert first.job == ReplyJob(2, "Data", "Tidewell", S.APPLIED)
    assert first.reviewed_at == LATER
    assert again.type is ReplyType.INVITATION
    assert again.job is None
    assert again.reviewed_at == LATER + timedelta(hours=1)
    # Автоматичне зіставлення лишається в записі: розбір його не стирає.
    assert (again.confidence, again.matched_by) == (Confidence.HIGH, MatchedBy.DOMAIN)
    assert [r.id for r in portal.call(listed, uow, ALICE, True)] == [1]


def test_texts_are_returned_only_for_the_users_own_mail(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(store_mail, uow, ALICE, "g1")
    portal.call(store_mail, uow, BOB, "g2")

    async def run() -> tuple[dict[int, str], dict[int, str]]:
        async with uow() as tx:
            return (
                await tx.mail_messages.texts(ALICE, [1, 2, 99]),
                await tx.mail_messages.texts(ALICE, []),
            )

    mine, nothing = portal.call(run)

    assert mine == {1: "Could we schedule a call?"}
    assert nothing == {}


def test_deleting_a_job_keeps_the_reply_without_a_job_and_deleting_a_mail_removes_it(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_jobs, uow)
    portal.call(store_mail, uow, ALICE, "g1")
    portal.call(store_mail, uow, ALICE, "g2")
    portal.call(add_reply, uow, ALICE, 1, 1)
    portal.call(add_reply, uow, ALICE, 2, 2)

    async def delete() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM jobs WHERE user_id = :user AND job_number = 1"),
                {"user": ALICE.value},
            )
            await conn.execute(text("DELETE FROM mail_messages WHERE gmail_id = 'g2'"))

    portal.call(delete)

    assert rows(portal, engine, "SELECT mail_id, job_id FROM job_replies") == [
        (1, None)
    ]


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO job_replies (user_id, mail_id, suggested_type, confidence) "
        "SELECT user_id, id, 'other', 'bogus' FROM mail_messages",
        "INSERT INTO job_replies (user_id, mail_id, suggested_type, matched_by) "
        "SELECT user_id, id, 'other', 'bogus' FROM mail_messages",
        "INSERT INTO job_replies (user_id, mail_id, suggested_type, type) "
        "SELECT user_id, id, 'other', 'bogus' FROM mail_messages",
        "INSERT INTO job_replies (user_id, mail_id, suggested_type) "
        "SELECT user_id, id, 'bogus' FROM mail_messages",
    ],
    ids=["confidence", "matched_by", "type", "suggested_type"],
)
def test_unknown_values_are_refused_by_the_database(
    portal: BlockingPortal,
    engine: AsyncEngine,
    uow: UnitOfWorkFactory,
    statement: str,
) -> None:
    portal.call(store_mail, uow, ALICE, "g1")

    async def insert() -> None:
        async with engine.begin() as conn:
            await conn.execute(text(statement))

    with pytest.raises(IntegrityError):
        portal.call(insert)


def test_the_table_keeps_every_v1_column_for_the_etl(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    columns = {
        name
        for (name,) in rows(
            portal,
            engine,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'job_replies'",
        )
    }

    assert columns >= V1_REPLY_COLUMNS | {"id", "user_id", "mail_id", "job_id"}


def _letter(gmail_id: str, to: str, sender: str, **fields: object) -> IncomingMail:
    base = mail(gmail_id, to)
    return replace(
        base,
        from_address=sender,
        auth_headers=auth_headers(sender),
        received_at=NOW - timedelta(hours=1),
        **fields,  # type: ignore[arg-type]
    )


def test_sync_matches_company_mail_to_the_users_application_and_moves_it_to_replied(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_jobs, uow)

    async def address() -> str:
        async with uow() as tx:
            inbox = await tx.mail_inboxes.ensure(ALICE)
            await tx.commit()
        return personal_address(MAILBOX, inbox.tag)

    to = portal.call(address)
    box = FakeMailbox()
    box.deliver(
        _letter("g1", to, "hr@acme.com", text="Unfortunately, no."),
        _letter("g2", to, "news@startupjobs.example", subject="25 roles"),
    )

    report = portal.call(
        MailSyncUseCases(uow, FakeClock(NOW), RandomIds()).sync_mail, box, MAILBOX
    )

    assert (report.replies.matched, report.replies.unmatched) == (1, 1)
    assert report.replies.replied == 1
    assert rows(
        portal,
        engine,
        "SELECT j.title, r.confidence, r.matched_by, r.suggested_type, a.status "
        "FROM job_replies r JOIN jobs j ON j.id = r.job_id "
        "JOIN applications a ON a.job_id = j.id",
    ) == [("Backend", "high", "email", "rejection", "replied")]
    assert rows(
        portal, engine, "SELECT count(*) FROM job_replies WHERE job_id IS NULL"
    ) == [(1,)]
