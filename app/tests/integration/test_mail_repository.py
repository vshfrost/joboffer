"""Пошта на справжній базі: особисті адреси, листи, відкинуті листи, стан синку й лок, синк."""

from datetime import UTC, datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from application.mail.sync import MailSyncUseCases
from domain.mail.mail import (
    TAG_PATTERN,
    Attachment,
    DroppedRecord,
    DropReason,
    IncomingMail,
    MailCategory,
    MailSyncState,
    personal_address,
)
from domain.mail.sender_auth import SenderAuth
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from infrastructure.system import RandomIds
from tests.integration.test_jobs_repository import ALICE, BOB, uow
from tests.support import linkedin_alerts
from tests.support.clock import FakeClock
from tests.support.mail import FakeMailbox, auth_headers

__all__ = ["uow"]

MAILBOX = "mailroom@example.com"
NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)
VERIFIED = SenderAuth.VERIFIED

# Усі поля таблиць пошти (крім ключів): ETL у B12 переносить їх без втрат.
V1_MAIL_MESSAGE_COLUMNS = {
    "gmail_id",
    "message_id",
    "in_reply_to",
    "reference_ids",
    "from_address",
    "from_name",
    "to_addresses",
    "subject",
    "sent_at",
    "received_at",
    "category",
    "sender_auth",
    "untrusted_text",
    "attachments",
    "parse_error",
    "created_at",
}


@pytest.fixture(autouse=True)
def _clean_sync_state(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    """`mail_sync_state` не пов'язана з users: без очищення курсор попереднього тесту лишається."""

    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE mail_sync_state"))

    portal.call(clean)


def mail(gmail_id: str, to: str = "", *, hours_ago: int = 1) -> IncomingMail:
    return IncomingMail(
        id=gmail_id,
        received_at=NOW - timedelta(hours=hours_ago),
        message_id=f"<{gmail_id}@acme.example>",
        in_reply_to="<application@example.com>",
        references=("<thread@acme.example>", "<application@example.com>"),
        from_address="talent@acme.example",
        from_name="María",
        to=("taras@example.com",),
        delivered_to=(to,),
        subject="Re: next steps",
        sent_at=NOW - timedelta(hours=2),
        text="Could we schedule a call?",
        attachments=(Attachment("task.pdf", "application/pdf", 15),),
        parse_error="",
    )


def run_sync(
    portal: BlockingPortal, factory: UnitOfWorkFactory, box: FakeMailbox
) -> object:
    use_cases = MailSyncUseCases(factory, FakeClock(NOW), RandomIds())
    return portal.call(use_cases.sync_mail, box, MAILBOX)


def rows(
    portal: BlockingPortal, engine: AsyncEngine, sql: str
) -> list[tuple[object, ...]]:
    async def fetch() -> list[tuple[object, ...]]:
        async with engine.connect() as conn:
            return [tuple(row) for row in await conn.execute(text(sql))]

    return portal.call(fetch)


def test_inbox_is_created_once_with_a_random_tag(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[object, ...]:
        async with uow() as tx:
            first = await tx.mail_inboxes.ensure(ALICE)
            await tx.commit()
        async with uow() as tx:
            again = await tx.mail_inboxes.ensure(ALICE)
            theirs = await tx.mail_inboxes.ensure(BOB)
            await tx.commit()
        async with uow() as tx:
            return (
                first,
                again,
                theirs,
                await tx.mail_inboxes.owner(first.tag),
                await tx.mail_inboxes.owner(theirs.tag),
                await tx.mail_inboxes.owner("zzzzzzzzzzzz"),
            )

    first, again, theirs, owner_a, owner_b, nobody = portal.call(run)

    assert TAG_PATTERN.fullmatch(first.tag)  # type: ignore[attr-defined]
    assert again == first
    assert theirs.tag != first.tag  # type: ignore[attr-defined]
    assert (owner_a, owner_b, nobody) == (ALICE, BOB, None)


def test_rotation_retires_the_old_tag_for_its_owner(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[object, ...]:
        async with uow() as tx:
            old = await tx.mail_inboxes.ensure(ALICE)
            new = await tx.mail_inboxes.rotate(ALICE)
            await tx.commit()
        async with uow() as tx:
            return (
                old,
                new,
                await tx.mail_inboxes.owner(old.tag),
                await tx.mail_inboxes.owner(new.tag),
                await tx.mail_inboxes.retired_owner(old.tag),
                await tx.mail_inboxes.retired_owner(new.tag),
            )

    old, new, old_owner, new_owner, retired, not_retired = portal.call(run)

    assert new.tag != old.tag  # type: ignore[attr-defined]
    assert new.rotated_at is not None  # type: ignore[attr-defined]
    assert (old_owner, new_owner) == (None, ALICE)
    assert (retired, not_retired) == (ALICE, None)


def test_a_message_is_stored_once_with_all_fields(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    letter = mail("g1")

    async def run() -> tuple[bool, bool, set[str], set[str]]:
        async with uow() as tx:
            first = await tx.mail_messages.add(
                ALICE, letter, MailCategory.COMPANY, VERIFIED
            )
            await tx.commit()
        async with uow() as tx:
            again = await tx.mail_messages.add(
                ALICE, letter, MailCategory.OTHER, SenderAuth.FAILED
            )
            known = await tx.mail_messages.known(["g1", "g2"])
            nothing = await tx.mail_messages.known([])
        return first, again, known, nothing

    first, again, known, nothing = portal.call(run)

    assert (first, again, known, nothing) == (True, False, {"g1"}, set())

    async def fetch() -> dict[str, object]:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT * FROM mail_messages"))
            return dict(result.mappings().one())

    row = portal.call(fetch)
    assert row["user_id"] == ALICE.value
    assert row["category"] == "company"
    assert row["sender_auth"] == "verified"
    assert row["message_id"] == "<g1@acme.example>"
    assert row["reference_ids"] == list(letter.references)
    assert row["to_addresses"] == ["taras@example.com"]
    assert row["untrusted_text"] == "Could we schedule a call?"
    assert row["attachments"] == [
        {"filename": "task.pdf", "content_type": "application/pdf", "size": 15}
    ]
    assert row["sent_at"] == letter.sent_at
    assert row["received_at"] == letter.received_at
    assert set(row) >= V1_MAIL_MESSAGE_COLUMNS


def test_count_received_is_per_user_and_excludes_the_window_start(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[int, int, int]:
        async with uow() as tx:
            for gmail_id, user_id, hours in (
                ("a1", ALICE, 1),
                ("a5", ALICE, 5),
                ("a30", ALICE, 30),
                ("b1", BOB, 1),
            ):
                await tx.mail_messages.add(
                    user_id,
                    mail(gmail_id, hours_ago=hours),
                    MailCategory.COMPANY,
                    VERIFIED,
                )
            await tx.commit()
        async with uow() as tx:
            repo = tx.mail_messages
            day = await repo.count_received(ALICE, NOW - timedelta(hours=24), NOW)
            edge = await repo.count_received(ALICE, NOW - timedelta(hours=5), NOW)
            theirs = await repo.count_received(BOB, NOW - timedelta(hours=24), NOW)
        return day, edge, theirs

    assert portal.call(run) == (2, 1, 1)


def test_a_dropped_mail_is_recorded_once_without_text(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    record = DroppedRecord(
        "d1", DropReason.RETIRED_TAG, NOW - timedelta(hours=3), "spam@x.example", "Hi"
    )

    async def run() -> tuple[set[str], set[str]]:
        async with uow() as tx:
            await tx.mail_dropped.add(ALICE, record)
            await tx.mail_dropped.add(
                BOB, DroppedRecord("e1", DropReason.DAILY_LIMIT, NOW, "b@x.example", "")
            )
            await tx.mail_dropped.add(ALICE, record)  # той самий лист удруге
            await tx.commit()
        async with uow() as tx:
            return (
                await tx.mail_dropped.known(["d1", "e1", "x1"]),
                await tx.mail_dropped.known([]),
            )

    known, nothing = portal.call(run)

    assert (known, nothing) == ({"d1", "e1"}, set())
    stored = rows(
        portal,
        engine,
        "SELECT gmail_id, reason, from_address, subject FROM mail_dropped ORDER BY gmail_id",
    )
    assert stored == [
        ("d1", "retired_tag", "spam@x.example", "Hi"),
        ("e1", "daily_limit", "b@x.example", ""),
    ]
    columns = {
        name
        for (name,) in rows(
            portal,
            engine,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'mail_dropped'",
        )
    }
    assert not {"text", "untrusted_text", "body"} & columns


def test_sync_state_keeps_the_cursor_and_the_last_error(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    later = NOW + timedelta(minutes=30)

    async def run() -> list[MailSyncState | None]:
        seen: list[MailSyncState | None] = []
        async with uow() as tx:
            seen.append(await tx.mail_sync.get(MAILBOX))
            await tx.mail_sync.fail(MAILBOX, "down", NOW)
            seen.append(await tx.mail_sync.get(MAILBOX))
            await tx.mail_sync.save(MAILBOX, "42", later)
            await tx.commit()
        async with uow() as tx:
            seen.append(await tx.mail_sync.get(MAILBOX))
            await tx.mail_sync.fail(MAILBOX, "again", later)
            seen.append(await tx.mail_sync.get(MAILBOX))
        return seen

    assert portal.call(run) == [
        None,
        MailSyncState(last_error="down", failed_at=NOW),
        MailSyncState(history_id="42", synced_at=later, failed_at=NOW),
        MailSyncState(
            history_id="42", synced_at=later, last_error="again", failed_at=later
        ),
    ]


def test_only_one_sync_holds_the_lock(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[bool, bool, bool]:
        async with uow() as first:
            held = await first.mail_sync.lock()
            async with uow() as second:
                blocked = await second.mail_sync.lock()
        async with uow() as third:
            freed = await third.mail_sync.lock()
        return held, blocked, freed

    assert portal.call(run) == (True, False, True)


def test_sync_routes_mail_to_its_owner_only_and_is_repeatable(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    async def addresses() -> tuple[str, str]:
        async with uow() as tx:
            a = await tx.mail_inboxes.ensure(ALICE)
            b = await tx.mail_inboxes.ensure(BOB)
            await tx.commit()
        return personal_address(MAILBOX, a.tag), personal_address(MAILBOX, b.tag)

    to_a, to_b = portal.call(addresses)
    box = FakeMailbox()
    box.deliver(
        mail("a1", to_a),
        mail("b1", to_b),
        mail("x1", "mailroom+zzzzzzzzzzzz@example.com"),
    )

    first = run_sync(portal, uow, box)
    again = run_sync(portal, uow, box)

    assert first.stored == 2  # type: ignore[attr-defined]
    assert [d.reason for d in first.dropped] == [DropReason.UNKNOWN_TAG]  # type: ignore[attr-defined]
    assert again.stored == 0  # type: ignore[attr-defined]
    stored = rows(
        portal,
        engine,
        "SELECT gmail_id, user_id, category FROM mail_messages ORDER BY id",
    )
    assert stored == [
        ("a1", ALICE.value, "company"),
        ("b1", BOB.value, "company"),
    ]
    assert rows(portal, engine, "SELECT count(*) FROM mail_dropped") == [(0,)]


def test_sync_records_a_retired_address_mail_for_its_owner(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    async def prepare() -> tuple[str, str]:
        async with uow() as tx:
            old = await tx.mail_inboxes.ensure(ALICE)
            new = await tx.mail_inboxes.rotate(ALICE)
            await tx.commit()
        return personal_address(MAILBOX, old.tag), personal_address(MAILBOX, new.tag)

    old, new = portal.call(prepare)
    box = FakeMailbox()
    box.deliver(mail("old1", old), mail("new1", new))

    first = run_sync(portal, uow, box)
    again = run_sync(portal, uow, box)

    assert [(d.gmail_id, d.reason) for d in first.dropped] == [  # type: ignore[attr-defined]
        ("old1", DropReason.RETIRED_TAG)
    ]
    assert again.dropped == []  # type: ignore[attr-defined]
    assert rows(portal, engine, "SELECT gmail_id FROM mail_messages") == [("new1",)]
    assert rows(
        portal,
        engine,
        "SELECT gmail_id, user_id, reason, from_address, subject FROM mail_dropped",
    ) == [("old1", ALICE.value, "retired_tag", "talent@acme.example", "Re: next steps")]


def test_the_database_rejects_unknown_values_and_repeated_gmail_ids(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def insert_message(category: str, auth: str, gmail_id: str) -> None:
        async with uow() as tx:
            await tx.session.execute(
                text(
                    "INSERT INTO mail_messages (user_id, gmail_id, received_at, category, "
                    "sender_auth, attachments) VALUES (:u, :g, now(), :c, :a, '[]')"
                ),
                {"u": ALICE.value, "g": gmail_id, "c": category, "a": auth},
            )
            await tx.commit()

    async def insert_dropped(reason: str) -> None:
        async with uow() as tx:
            await tx.session.execute(
                text(
                    "INSERT INTO mail_dropped (user_id, gmail_id, reason, received_at) "
                    "VALUES (:u, 'd', :r, now())"
                ),
                {"u": ALICE.value, "r": reason},
            )
            await tx.commit()

    portal.call(insert_message, "company", "verified", "ok")
    for args in (
        ("newsletter", "verified", "g1"),
        ("company", "maybe", "g2"),
        ("company", "verified", "ok"),
    ):
        with pytest.raises(IntegrityError):
            portal.call(insert_message, *args)
    with pytest.raises(IntegrityError):
        portal.call(insert_dropped, "no_tag")


def test_deleting_a_user_deletes_their_mail(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    async def run() -> None:
        async with uow() as tx:
            inbox = await tx.mail_inboxes.ensure(ALICE)
            await tx.mail_inboxes.rotate(ALICE)
            await tx.mail_messages.add(
                ALICE, mail("a1", inbox.tag), MailCategory.COMPANY, VERIFIED
            )
            await tx.mail_dropped.add(
                ALICE, DroppedRecord("d1", DropReason.DAILY_LIMIT, NOW, "x@y.z", "s")
            )
            await tx.commit()
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM users WHERE id = :id"), {"id": ALICE.value}
            )

    portal.call(run)

    for table_count in (
        "SELECT count(*) FROM mail_inboxes",
        "SELECT count(*) FROM mail_retired_tags",
        "SELECT count(*) FROM mail_messages",
        "SELECT count(*) FROM mail_dropped",
    ):
        assert rows(portal, engine, table_count) == [(0,)]


def alert_mail(gmail_id: str, to: str, body: str) -> IncomingMail:
    sender = "jobalerts-noreply@linkedin.com"
    return IncomingMail(
        id=gmail_id,
        received_at=NOW - timedelta(hours=1),
        from_address=sender,
        auth_headers=auth_headers(sender),
        delivered_to=(to,),
        subject="Нові вакансії",
        text=body,
    )


def alice_address(portal: BlockingPortal, factory: UnitOfWorkFactory) -> str:
    async def address() -> str:
        async with factory() as tx:
            inbox = await tx.mail_inboxes.ensure(ALICE)
            await tx.commit()
        return personal_address(MAILBOX, inbox.tag)

    return portal.call(address)


def test_sync_turns_an_alert_mail_into_needs_text_jobs_exactly_once(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    box = FakeMailbox()
    box.deliver(alert_mail("al1", alice_address(portal, uow), linkedin_alerts.SPAIN))

    first = run_sync(portal, uow, box)
    again = run_sync(portal, uow, box)

    report = first.alerts  # type: ignore[attr-defined]
    assert (report.alerts, report.created, report.known, report.failed) == (1, 6, 0, 0)
    assert again.alerts.alerts == 0  # type: ignore[attr-defined]
    jobs = rows(
        portal,
        engine,
        "SELECT job_number, user_id, source, title, company, location, url, "
        "linkedin_id, text FROM jobs ORDER BY job_number",
    )
    assert len(jobs) == 6
    assert jobs[0] == (
        1,
        ALICE.value,
        "linkedin_alert",
        "Senior Software Engineer, Back-end (Fraud)",
        "Affirm",
        "Spain",
        "https://www.linkedin.com/jobs/view/4442068661",
        "4442068661",
        None,
    )
    assert rows(portal, engine, "SELECT parse_error FROM mail_messages") == [("",)]


def test_sync_records_a_parse_error_on_the_alert_mail_and_does_not_fail(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    box = FakeMailbox()
    box.deliver(alert_mail("al1", alice_address(portal, uow), "Привіт, без вакансій."))

    report = run_sync(portal, uow, box)

    assert report.alerts.failed == 1  # type: ignore[attr-defined]
    assert rows(portal, engine, "SELECT count(*) FROM jobs") == [(0,)]
    assert rows(portal, engine, "SELECT parse_error FROM mail_messages") == [
        ("linkedin_alert: вакансій не знайдено (невідомий шаблон)",)
    ]
