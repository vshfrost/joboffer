"""Прогін джерел на справжній базі: увімкнені джерела всіх користувачів, стан (один рядок на
джерело користувача), лок прогону, унікальність і допустимі значення в таблицях."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.sources.failure import FailureReason
from domain.sources.ids import SourceId
from domain.sources.importing import ImportSummary
from domain.sources.kinds import FeedSource, Platform
from domain.sources.run import SourceRun, Subscription
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, uow

__all__ = ["uow"]

RAN_AT = datetime(2026, 10, 26, 8, 30, tzinfo=UTC)
LATER = datetime(2026, 10, 26, 14, 30, tzinfo=UTC)
SUMMARY = ImportSummary(found=7, imported=3, filtered=2, duplicate=1, completed=1)


class Db:
    """Прямі SQL-запити: наповнення таблиць (керування ними — K45) і читання стану."""

    def __init__(self, portal: BlockingPortal, engine: AsyncEngine) -> None:
        self._portal = portal
        self._engine = engine
        self._next = 0

    def execute(self, sql: str, **params: Any) -> None:
        async def run() -> None:
            async with self._engine.begin() as conn:
                await conn.execute(text(sql), params)

        self._portal.call(run)

    def rows(self, sql: str, **params: Any) -> list[tuple[Any, ...]]:
        async def run() -> list[tuple[Any, ...]]:
            async with self._engine.connect() as conn:
                return [tuple(row) for row in await conn.execute(text(sql), params)]

        return self._portal.call(run)

    def _new_id(self) -> UUID:
        self._next += 1
        return UUID(int=1000 + self._next)

    def company(
        self,
        user: UUID,
        platform: str,
        slug: str,
        *,
        name: str = "",
        enabled: bool = True,
    ) -> UUID:
        company_id = self._new_id()
        self.execute(
            "INSERT INTO source_companies (id, user_id, platform, slug, name, enabled)"
            " VALUES (:id, :user, :platform, :slug, :name, :enabled)",
            id=company_id,
            user=user,
            platform=platform,
            slug=slug,
            name=name,
            enabled=enabled,
        )
        return company_id

    def feed(
        self, user: UUID, source: str, query: str, *, enabled: bool = True
    ) -> UUID:
        feed_id = self._new_id()
        self.execute(
            "INSERT INTO source_feeds (id, user_id, source, query, enabled)"
            " VALUES (:id, :user, :source, :query, :enabled)",
            id=feed_id,
            user=user,
            source=source,
            query=query,
            enabled=enabled,
        )
        return feed_id


@pytest.fixture
def db(portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory) -> Db:
    # `uow` очищає users CASCADE, а з ними й джерела та їх стани.
    return Db(portal, engine)


COMPANY_RUNS = (
    "SELECT company_id, ran_at, found, imported, filtered, duplicate, completed, error"
    " FROM source_company_runs ORDER BY 1"
)
FEED_RUNS = (
    "SELECT feed_id, ran_at, found, imported, filtered, duplicate, completed, error"
    " FROM source_feed_runs ORDER BY 1"
)


# --- що читати ------------------------------------------------------------------------------


def test_enabled_lists_enabled_companies_and_feeds_of_all_users(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    acme = db.company(ALICE.value, "greenhouse", "acme", name="Acme")
    globex = db.company(BOB.value, "lever", "globex", name="Globex Inc")
    python = db.feed(ALICE.value, "dou", "category=Python")
    db.company(ALICE.value, "ashby", "initech", name="Initech", enabled=False)
    db.feed(BOB.value, "djinni", "primary_keyword=Python", enabled=False)

    async def run() -> list[Subscription]:
        async with uow() as tx:
            return await tx.source_runs.enabled()

    found = portal.call(run)

    assert {(s.id, s.user_id, s.kind, s.ref, s.name) for s in found} == {
        (SourceId(acme), ALICE, Platform.GREENHOUSE, "acme", "Acme"),
        (SourceId(globex), BOB, Platform.LEVER, "globex", "Globex Inc"),
        (SourceId(python), ALICE, FeedSource.DOU, "category=Python", ""),
    }


def test_enabled_is_empty_without_sources(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    async def run() -> list[Subscription]:
        async with uow() as tx:
            return await tx.source_runs.enabled()

    assert portal.call(run) == []


# --- стан прогону: один рядок на джерело користувача ----------------------------------------


def save(
    portal: BlockingPortal,
    uow: UnitOfWorkFactory,
    subscription: Subscription,
    run: SourceRun,
) -> None:
    async def go() -> None:
        async with uow() as tx:
            await tx.source_runs.save(subscription, run)
            await tx.commit()

    portal.call(go)


def test_company_run_is_saved_with_time_counters_and_error(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    company = db.company(ALICE.value, "greenhouse", "acme", name="Acme")
    sub = Subscription(SourceId(company), ALICE, Platform.GREENHOUSE, "acme", "Acme")

    save(portal, uow, sub, SourceRun(RAN_AT, SUMMARY))

    assert db.rows(COMPANY_RUNS) == [(company, RAN_AT, 7, 3, 2, 1, 1, None)]


def test_feed_run_is_saved_with_time_counters_and_error(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    feed = db.feed(ALICE.value, "dou", "category=Python")
    sub = Subscription(SourceId(feed), ALICE, FeedSource.DOU, "category=Python")

    save(portal, uow, sub, SourceRun(RAN_AT, error=FailureReason.RATE_LIMITED))

    assert db.rows(FEED_RUNS) == [(feed, RAN_AT, 0, 0, 0, 0, 0, "rate_limited")]


@pytest.mark.parametrize("kind", ["company", "feed"])
def test_a_new_run_replaces_the_old_one_in_the_same_row(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db, kind: str
) -> None:
    if kind == "company":
        row = db.company(ALICE.value, "greenhouse", "acme", name="Acme")
        sub = Subscription(SourceId(row), ALICE, Platform.GREENHOUSE, "acme", "Acme")
        runs = COMPANY_RUNS
    else:
        row = db.feed(ALICE.value, "dou", "category=Python")
        sub = Subscription(SourceId(row), ALICE, FeedSource.DOU, "category=Python")
        runs = FEED_RUNS
    save(portal, uow, sub, SourceRun(RAN_AT, error=FailureReason.TIMEOUT))

    save(portal, uow, sub, SourceRun(LATER, SUMMARY))

    assert db.rows(runs) == [(row, LATER, 7, 3, 2, 1, 1, None)]


def test_runs_of_two_users_for_the_same_target_are_separate_rows(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    mine = db.company(ALICE.value, "greenhouse", "acme", name="Acme")
    theirs = db.company(BOB.value, "greenhouse", "acme", name="Acme")
    save(
        portal,
        uow,
        Subscription(SourceId(mine), ALICE, Platform.GREENHOUSE, "acme", "Acme"),
        SourceRun(RAN_AT, SUMMARY),
    )
    save(
        portal,
        uow,
        Subscription(SourceId(theirs), BOB, Platform.GREENHOUSE, "acme", "Acme"),
        SourceRun(RAN_AT, error=FailureReason.NOT_FOUND),
    )

    rows = db.rows(COMPANY_RUNS)

    assert sorted(rows) == sorted(
        [
            (mine, RAN_AT, 7, 3, 2, 1, 1, None),
            (theirs, RAN_AT, 0, 0, 0, 0, 0, "not_found"),
        ]
    )


def test_deleting_a_source_removes_its_run_state(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    company = db.company(ALICE.value, "greenhouse", "acme", name="Acme")
    feed = db.feed(ALICE.value, "dou", "category=Python")
    save(
        portal,
        uow,
        Subscription(SourceId(company), ALICE, Platform.GREENHOUSE, "acme", "Acme"),
        SourceRun(RAN_AT, SUMMARY),
    )
    save(
        portal,
        uow,
        Subscription(SourceId(feed), ALICE, FeedSource.DOU, "category=Python"),
        SourceRun(RAN_AT, SUMMARY),
    )

    db.execute("DELETE FROM source_companies WHERE id = :id", id=company)
    db.execute("DELETE FROM source_feeds WHERE id = :id", id=feed)

    assert db.rows(COMPANY_RUNS) == []
    assert db.rows(FEED_RUNS) == []


def test_deleting_a_user_removes_their_sources_and_run_state(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    company = db.company(ALICE.value, "greenhouse", "acme", name="Acme")
    save(
        portal,
        uow,
        Subscription(SourceId(company), ALICE, Platform.GREENHOUSE, "acme", "Acme"),
        SourceRun(RAN_AT, SUMMARY),
    )

    db.execute("DELETE FROM users WHERE id = :id", id=ALICE.value)

    assert db.rows("SELECT id FROM source_companies") == []
    assert db.rows(COMPANY_RUNS) == []


# --- лок прогону ----------------------------------------------------------------------------


def test_only_one_run_holds_the_lock(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[bool, bool, bool]:
        async with uow() as first:
            held = await first.source_runs.lock()
            async with uow() as second:
                blocked = await second.source_runs.lock()
        async with uow() as third:
            freed = await third.source_runs.lock()
        return held, blocked, freed

    assert portal.call(run) == (True, False, True)


def test_the_run_lock_does_not_block_the_mail_sync(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[bool, bool]:
        async with uow() as first:
            runs = await first.source_runs.lock()
            async with uow() as second:
                mail = await second.mail_sync.lock()
        return runs, mail

    assert portal.call(run) == (True, True)


# --- унікальність і допустимі значення ------------------------------------------------------


def test_a_user_cannot_have_the_same_platform_and_slug_twice(db: Db) -> None:
    db.company(ALICE.value, "greenhouse", "acme")

    with pytest.raises(IntegrityError):
        db.company(ALICE.value, "greenhouse", "acme")


def test_the_same_slug_is_allowed_for_another_user_or_platform(db: Db) -> None:
    db.company(ALICE.value, "greenhouse", "acme")

    db.company(BOB.value, "greenhouse", "acme")
    db.company(ALICE.value, "lever", "acme")

    assert len(db.rows("SELECT id FROM source_companies")) == 3


def test_a_user_cannot_have_the_same_feed_source_and_query_twice(db: Db) -> None:
    db.feed(ALICE.value, "dou", "category=Python")

    with pytest.raises(IntegrityError):
        db.feed(ALICE.value, "dou", "category=Python")


def test_the_same_query_is_allowed_for_another_user_or_source(db: Db) -> None:
    db.feed(ALICE.value, "dou", "category=Python")

    db.feed(BOB.value, "dou", "category=Python")
    db.feed(ALICE.value, "djinni", "category=Python")

    assert len(db.rows("SELECT id FROM source_feeds")) == 3


def test_an_unknown_platform_is_rejected(db: Db) -> None:
    with pytest.raises(IntegrityError):
        db.company(ALICE.value, "workday", "acme")


def test_an_unknown_feed_source_is_rejected(db: Db) -> None:
    with pytest.raises(IntegrityError):
        db.feed(ALICE.value, "indeed", "q=python")


def test_an_unknown_error_code_is_rejected(db: Db) -> None:
    company = db.company(ALICE.value, "greenhouse", "acme")

    with pytest.raises(IntegrityError):
        db.execute(
            "INSERT INTO source_company_runs"
            " (company_id, ran_at, found, imported, filtered, duplicate, completed, error)"
            " VALUES (:id, now(), 0, 0, 0, 0, 0, 'boom')",
            id=company,
        )
