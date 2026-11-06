"""«Вхідні» на справжній базі: пошук і вид, відкинуті листи в списку, сторінки, читання, останній
лист категорії, підозрілі, лічильники відкинутих, запити синку вручну; ізоляція користувачів."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.identity.ids import UserId
from domain.mail.inbox import DroppedSummary, MailPage, MailQuery, StoredMail
from domain.mail.mail import DroppedRecord, DropReason, MailCategory
from domain.mail.sender_auth import SenderAuth
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB
from tests.integration.test_mail_repository import (
    NOW,
    VERIFIED,
    _clean_sync_state,
    mail,
    rows,
    uow,
)

__all__ = ["_clean_sync_state", "uow"]

SINCE = NOW - timedelta(days=30)


async def seed(factory: UnitOfWorkFactory) -> None:
    """Листи Alice: a1 (1 год) company, a2 (2 год) alert, a3 (3 год) confirmation, a4 (4 год)
    suspicious; відкинуті: d1 (1.5 год), d0 (40 днів). Лист Bob: b1."""
    async with factory() as tx:
        spec = (
            (ALICE, "a1", 1, MailCategory.COMPANY, "talent@acme.example", "Offer 100%"),
            (
                ALICE,
                "a2",
                2,
                MailCategory.LINKEDIN_ALERT,
                "jobalerts-noreply@linkedin.com",
                "Alert",
            ),
            (
                ALICE,
                "a3",
                3,
                MailCategory.FORWARDING_CONFIRMATION,
                "forwarding-noreply@google.com",
                "(#1) Gmail",
            ),
            (ALICE, "a4", 4, MailCategory.SUSPICIOUS, "fake@acme.example", "Forged"),
            (BOB, "b1", 1, MailCategory.COMPANY, "talent@acme.example", "Bob's secret"),
        )
        for user_id, gmail_id, hours, category, sender, subject in spec:
            letter = mail(gmail_id, hours_ago=hours)
            letter = replace(letter, from_address=sender, subject=subject)
            await tx.mail_messages.add(user_id, letter, category, VERIFIED)
        await tx.mail_dropped.add(
            ALICE,
            DroppedRecord(
                "d1",
                DropReason.DAILY_LIMIT,
                NOW - timedelta(minutes=90),
                "spam@x.example",
                "Win",
            ),
        )
        await tx.mail_dropped.add(
            ALICE,
            DroppedRecord(
                "d0",
                DropReason.RETIRED_TAG,
                NOW - timedelta(days=40),
                "old@x.example",
                "Old",
            ),
        )
        await tx.commit()


@pytest.fixture
def seeded(portal: BlockingPortal, uow: UnitOfWorkFactory) -> UnitOfWorkFactory:
    portal.call(seed, uow)
    return uow


def search(
    portal: BlockingPortal,
    factory: UnitOfWorkFactory,
    user_id: UserId,
    **fields: object,
) -> list[tuple[str, bool]]:
    query = MailQuery.parse(**fields)  # type: ignore[arg-type]

    async def run() -> list[tuple[str, bool]]:
        async with factory() as tx:
            found = await tx.mail_messages.search(user_id, query, SINCE)
        return [(item.subject, item.dropped) for item in found.items]

    return portal.call(run)


def test_the_list_mixes_stored_and_recent_dropped_mail_newest_first(
    portal: BlockingPortal, seeded: UnitOfWorkFactory
) -> None:
    assert search(portal, seeded, ALICE) == [
        ("Offer 100%", False),
        ("Win", True),
        ("Alert", False),
        ("(#1) Gmail", False),
        ("Forged", False),
    ]


def test_the_list_never_shows_the_mail_of_another_user(
    portal: BlockingPortal, seeded: UnitOfWorkFactory
) -> None:
    assert search(portal, seeded, BOB) == [("Bob's secret", False)]
    assert search(portal, seeded, ALICE, text="secret") == []


@pytest.mark.parametrize(
    ("kind", "subjects"),
    [
        ("company", ["Offer 100%"]),
        ("linkedin_alert", ["Alert"]),
        ("linkedin_message", []),
        ("forwarding_confirmation", ["(#1) Gmail"]),
        ("other", ["Forged"]),
        ("dropped", ["Win"]),
    ],
)
def test_the_kind_filter(
    portal: BlockingPortal,
    seeded: UnitOfWorkFactory,
    kind: str,
    subjects: list[str],
) -> None:
    assert [s for s, _ in search(portal, seeded, ALICE, kind=kind)] == subjects


@pytest.mark.parametrize(
    ("needle", "subjects"),
    [
        ("ACME", ["Offer 100%", "Forged"]),  # адреса відправника, без регістру
        ("spam@x", ["Win"]),  # відправник відкинутого
        ("%", ["Offer 100%"]),  # не шаблон
        ("_", []),
        ("schedule", ["Offer 100%", "Alert", "(#1) Gmail", "Forged"]),  # текст листів
        ("Old", []),  # відкинутий поза вікном
    ],
)
def test_the_text_search(
    portal: BlockingPortal,
    seeded: UnitOfWorkFactory,
    needle: str,
    subjects: list[str],
) -> None:
    assert [s for s, _ in search(portal, seeded, ALICE, text=needle)] == subjects


def test_pages_cut_the_list_and_keep_the_total(
    portal: BlockingPortal, seeded: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[MailPage, MailPage, int]:
        async with seeded() as tx:
            repo = tx.mail_messages
            first = await repo.search(ALICE, MailQuery(page=MailPage(1, 2)), SINCE)
            last = await repo.search(ALICE, MailQuery(page=MailPage(3, 2)), SINCE)
            beyond = await repo.search(ALICE, MailQuery(page=MailPage(9, 2)), SINCE)
        return first.page, last.page, len(beyond.items)

    first, last, beyond = portal.call(run)

    assert (first.total, first.first, first.last) == (5, 1, 2)
    assert (last.first, last.last, last.has_older) == (5, 5, False)
    assert beyond == 0


def test_a_stored_mail_is_read_with_its_text_and_only_by_its_owner(
    portal: BlockingPortal, seeded: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[StoredMail | None, StoredMail | None, StoredMail | None]:
        async with seeded() as tx:
            listing = await tx.mail_messages.search(ALICE, MailQuery(), SINCE)
            mine = next(i.id for i in listing.items if i.subject == "Alert")
            own = await tx.mail_messages.get(ALICE, mine)
            foreign = await tx.mail_messages.get(BOB, mine)
            missing = await tx.mail_messages.get(ALICE, mine + 1000)
        return own, foreign, missing

    own, foreign, missing = portal.call(run)

    assert own is not None
    assert own.text == "Could we schedule a call?"
    assert own.summary.category is MailCategory.LINKEDIN_ALERT
    assert own.summary.sender_auth is SenderAuth.VERIFIED
    assert (foreign, missing) == (None, None)


def test_recent_latest_and_suspicious(
    portal: BlockingPortal, seeded: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[
        list[str], str | None, bool, DroppedSummary, DroppedSummary
    ]:
        async with seeded() as tx:
            repo = tx.mail_messages
            recent = [m.subject for m in await repo.recent(ALICE, 3)]
            latest = await repo.latest(ALICE, MailCategory.FORWARDING_CONFIRMATION)
            none = await repo.latest(BOB, MailCategory.FORWARDING_CONFIRMATION)
            mine = await repo.suspicious(ALICE, SINCE)
            theirs = await repo.suspicious(BOB, SINCE)
        subject = None if latest is None else latest.summary.subject
        return recent, subject, none is None, mine, theirs

    recent, latest, no_latest_for_bob, mine, theirs = portal.call(run)

    assert recent == ["Offer 100%", "Alert", "(#1) Gmail"]
    assert latest == "(#1) Gmail"
    assert no_latest_for_bob
    assert (mine.count, mine.last_at) == (1, NOW - timedelta(hours=4))
    assert theirs.count == 0


def test_dropped_summary_counts_by_reason_user_and_window(
    portal: BlockingPortal, seeded: UnitOfWorkFactory
) -> None:
    async def run() -> list[DroppedSummary]:
        async with seeded() as tx:
            repo = tx.mail_dropped
            return [
                await repo.summary(ALICE, DropReason.DAILY_LIMIT, SINCE),
                await repo.summary(ALICE, DropReason.RETIRED_TAG, SINCE),
                await repo.summary(
                    ALICE, DropReason.RETIRED_TAG, NOW - timedelta(days=60)
                ),
                await repo.summary(BOB, DropReason.DAILY_LIMIT, SINCE),
            ]

    limit, retired_now, retired_all, bob = portal.call(run)

    assert (limit.count, limit.last_at) == (1, NOW - timedelta(minutes=90))
    assert retired_now.count == 0
    assert retired_all.count == 1
    assert bob.count == 0


def test_sync_requests_are_per_user_inside_the_window_and_get_handled(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[list[list[datetime]], int, int]:
        async with uow() as tx:
            repo = tx.mail_sync_requests
            await repo.add(ALICE, NOW - timedelta(minutes=40))
            await repo.add(ALICE, NOW - timedelta(minutes=10))
            await repo.add(BOB, NOW - timedelta(minutes=5))
            await tx.commit()
        async with uow() as tx:
            repo = tx.mail_sync_requests
            window = NOW - timedelta(minutes=30)
            seen = [await repo.since(ALICE, window), await repo.since(BOB, window)]
            handled = await repo.mark_handled(NOW)
            again = await repo.mark_handled(NOW + timedelta(minutes=1))
            await tx.commit()
        return seen, handled, again

    seen, handled, again = portal.call(run)

    assert seen == [[NOW - timedelta(minutes=10)], [NOW - timedelta(minutes=5)]]
    assert (handled, again) == (3, 0)
    done = rows(
        portal,
        engine,
        "SELECT count(*) FROM mail_sync_requests WHERE handled_at = '2026-10-14T12:00:00+00:00'",
    )
    assert done == [(3,)]
    assert rows(
        portal,
        engine,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'mail_sync_requests' AND column_name = 'handled_at'",
    ) == [("handled_at",)]
