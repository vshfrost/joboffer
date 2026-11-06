"""Запити «оновити зараз» і вакансії з джерел на справжній базі: запити за користувачем і вікном, позначка
«виконано» для всіх, каскад від користувача; вакансії, які може показати «уже не проходять фільтр»."""

from datetime import timedelta
from uuid import UUID

from anyio.from_thread import BlockingPortal
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, uow
from tests.integration.test_sources_repository import Db, db

__all__ = ["db", "uow"]


def test_the_requests_table_has_the_v1_columns_and_the_user_time_index(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    def read(conn: Connection) -> tuple[set[str], list[list[str | None]]]:
        found = inspect(conn)
        columns = {c["name"] for c in found.get_columns("source_refresh_requests")}
        indexes = [
            list(i["column_names"])
            for i in found.get_indexes("source_refresh_requests")
        ]
        return columns, indexes

    async def run() -> tuple[set[str], list[list[str | None]]]:
        async with engine.connect() as conn:
            return await conn.run_sync(read)

    columns, indexes = portal.call(run)

    assert columns == {"id", "user_id", "requested_at", "handled_at"}
    assert ["user_id", "requested_at"] in indexes


def test_requests_are_per_user_inside_the_window_and_all_get_handled(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    async def run() -> tuple[list[list[object]], int, int]:
        async with uow() as tx:
            repo = tx.source_refresh_requests
            await repo.add(ALICE, NOW - timedelta(minutes=40))
            await repo.add(ALICE, NOW - timedelta(minutes=10))
            await repo.add(BOB, NOW - timedelta(minutes=5))
            await tx.commit()
        async with uow() as tx:
            repo = tx.source_refresh_requests
            window = NOW - timedelta(minutes=30)
            seen: list[list[object]] = [
                list(await repo.since(ALICE, window)),
                list(await repo.since(BOB, window)),
            ]
            handled = await repo.mark_handled(NOW)
            again = await repo.mark_handled(NOW + timedelta(minutes=1))
            await tx.commit()
        return seen, handled, again

    seen, handled, again = portal.call(run)

    assert seen == [[NOW - timedelta(minutes=10)], [NOW - timedelta(minutes=5)]]
    assert (handled, again) == (3, 0)
    assert db.rows(
        "SELECT count(*) FROM source_refresh_requests WHERE handled_at = :at", at=NOW
    ) == [(3,)]


def test_deleting_a_user_deletes_their_requests(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    async def add() -> None:
        async with uow() as tx:
            await tx.source_refresh_requests.add(ALICE, NOW)
            await tx.source_refresh_requests.add(BOB, NOW)
            await tx.commit()

    portal.call(add)

    db.execute("DELETE FROM users WHERE id = :id", id=ALICE.value)

    assert db.rows("SELECT user_id FROM source_refresh_requests") == [(BOB.value,)]


def job(title: str, source: str, *, text: str | None = "Опис вакансії.") -> NewJob:
    return NewJob(
        text=None if text is None else f"{text} {title}",
        url=f"https://jobs.example/{title.replace(' ', '-')}",
        title=title,
        company="Acme",
        source=source,
    )


def test_source_jobs_are_my_untouched_ats_and_rss_jobs_with_a_text(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    async def seed() -> None:
        async with uow() as tx:
            for index, (user, new) in enumerate(
                [
                    (ALICE, job("Counted ats", "ats:greenhouse")),
                    (ALICE, job("Counted rss", "rss:dou")),
                    (ALICE, job("Manual", "manual")),
                    (ALICE, job("Alert", "linkedin_alert")),
                    (ALICE, job("No text", "ats:lever", text=None)),
                    (ALICE, job("Hidden", "ats:ashby")),
                    (ALICE, job("Analysed", "ats:ashby")),
                    (ALICE, job("Applied", "ats:ashby")),
                    (BOB, job("Foreign", "ats:greenhouse")),
                ],
                start=1,
            ):
                await tx.jobs.add(user, JobId(UUID(int=100 + index)), new, NOW)
            await tx.jobs.dismiss(ALICE, [6], "не цікаво", NOW)
            await tx.commit()

    portal.call(seed)
    db.execute(
        "INSERT INTO job_analyses (id, user_id, job_id, score, filters_passed, details, updated_at) "
        "VALUES (:id, :user, :job, 50, true, '{}'::jsonb, :now)",
        id=UUID(int=900),
        user=ALICE.value,
        job=UUID(int=107),
        now=NOW,
    )
    db.execute(
        "INSERT INTO applications (job_id, user_id, status, applied_on, channel, status_changed_at) "
        "VALUES (:job, :user, 'applied', '2026-01-01', 'email', :now)",
        job=UUID(int=108),
        user=ALICE.value,
        now=NOW,
    )

    async def read() -> tuple[list[str | None], list[str | None]]:
        async with uow() as tx:
            mine = await tx.jobs.source_jobs(ALICE)
            theirs = await tx.jobs.source_jobs(BOB)
        return [j.title for j in mine], [j.title for j in theirs]

    mine, theirs = portal.call(read)

    assert mine == ["Counted ats", "Counted rss"]
    assert theirs == ["Foreign"]
