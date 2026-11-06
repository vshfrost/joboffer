"""PostgresTriage на справжній базі: кандидати, лічильник, upsert, ізоляція, схема для ETL."""

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.analysis.analysis import JobAnalysis
from domain.analysis.ids import AnalysisId
from domain.applications.application import (
    ApplicationChannel,
    ApplicationStatus,
    NewApplication,
)
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.search import JobSearch
from domain.triage.ids import TriageId
from domain.triage.triage import Triage, TriageEntry, TriageVerdict
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, posting, uow

__all__ = ["uow"]

_ids = iter(range(1, 10_000))


def _id() -> UUID:
    return UUID(int=0xB000 + next(_ids))


# Усі колонки `job_triage` v1: ETL у B12 переносить їх без втрат.
V1_TRIAGE_COLUMNS = {"score", "verdict", "reason", "triaged_at"}


async def _add(
    uow: UnitOfWorkFactory,
    user: UserId,
    body: str | None,
    when: datetime = NOW,
) -> tuple[int, JobId]:
    job_id = JobId(_id())
    async with uow() as tx:
        number = await tx.jobs.add(user, job_id, posting(body), when)  # type: ignore[arg-type]
        await tx.commit()
    return number, job_id


async def _save(
    uow: UnitOfWorkFactory,
    user: UserId,
    job: tuple[int, JobId],
    score: int = 70,
    verdict: TriageVerdict = TriageVerdict.MAYBE,
    reason: str = "r",
    now: datetime = NOW,
) -> None:
    number, job_id = job
    async with uow() as tx:
        await tx.triage.save(
            user,
            [(TriageId(_id()), job_id, TriageEntry(number, score, verdict, reason))],
            now,
        )
        await tx.commit()


async def _apply(
    uow: UnitOfWorkFactory, user: UserId, number: int, status: ApplicationStatus
) -> None:
    async with uow() as tx:
        await tx.applications.save(
            user,
            number,
            NewApplication(
                applied_on=date(2026, 1, 1), channel=ApplicationChannel.EMAIL
            ),
            NOW,
        )
        if status is not ApplicationStatus.APPLIED:
            await tx.applications.set_status(user, number, status, NOW)
        await tx.commit()


async def _candidates(
    uow: UnitOfWorkFactory, user: UserId, limit: int = 20
) -> list[int]:
    async with uow() as tx:
        return [job.number for job in await tx.triage.candidates(user, limit)]


async def _pending(uow: UnitOfWorkFactory, user: UserId) -> int:
    async with uow() as tx:
        count: int = await tx.triage.pending(user)
        return count


async def _scalar(engine: AsyncEngine, sql: str) -> object:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar()


def test_candidates_are_the_newest_visible_jobs_with_text_and_no_triage(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    old = portal.call(_add, uow, ALICE, "old", NOW)
    new = portal.call(_add, uow, ALICE, "new", NOW + timedelta(hours=1))
    portal.call(_add, uow, ALICE, None, NOW + timedelta(hours=2))
    hidden = portal.call(_add, uow, ALICE, "hidden", NOW + timedelta(hours=3))
    done = portal.call(_add, uow, ALICE, "done", NOW + timedelta(hours=4))
    portal.call(_add, uow, BOB, "bobs", NOW)

    async def hide() -> None:
        async with uow() as tx:
            await tx.jobs.dismiss(ALICE, [hidden[0]], "r", NOW)
            await tx.commit()

    portal.call(hide)
    portal.call(_save, uow, ALICE, done)
    assert portal.call(_candidates, uow, ALICE) == [new[0], old[0]]
    assert portal.call(_pending, uow, ALICE) == 2


def test_candidates_respect_the_limit_but_pending_does_not(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    for index in range(5):
        portal.call(_add, uow, ALICE, f"job {index}", NOW + timedelta(minutes=index))
    assert portal.call(_candidates, uow, ALICE, 2) == [5, 4]
    assert portal.call(_pending, uow, ALICE) == 5


def test_equal_times_fall_back_to_the_higher_number_first(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    for index in range(3):
        portal.call(_add, uow, ALICE, f"job {index}", NOW)
    assert portal.call(_candidates, uow, ALICE) == [3, 2, 1]


def test_a_user_has_no_candidates_of_another(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, BOB, "bobs")
    assert portal.call(_candidates, uow, ALICE) == []
    assert portal.call(_pending, uow, ALICE) == 0


def test_a_repeated_save_overwrites_the_row_and_keeps_the_first_id(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    portal.call(_save, uow, ALICE, job, 10, TriageVerdict.SKIP, "first", NOW)
    first_id = portal.call(_scalar, engine, "SELECT id FROM job_triage")
    later = NOW + timedelta(days=1)
    portal.call(_save, uow, ALICE, job, 90, TriageVerdict.ANALYSE, "second", later)

    assert portal.call(_scalar, engine, "SELECT count(*) FROM job_triage") == 1
    assert portal.call(_scalar, engine, "SELECT id FROM job_triage") == first_id
    row = portal.call(
        _scalar,
        engine,
        "SELECT concat_ws('|', score, verdict, reason) FROM job_triage",
    )
    assert row == "90|analyse|second"
    assert portal.call(_scalar, engine, "SELECT triaged_at FROM job_triage") == later


def test_the_list_shows_the_triage_of_the_job(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    portal.call(_save, uow, ALICE, job, 33, TriageVerdict.SKIP, "Onsite Berlin")

    async def listed() -> tuple[object, ...]:
        async with uow() as tx:
            [item] = await tx.jobs.search(ALICE, JobSearch())
            return (item.triage_score, item.triage_verdict, item.triage_reason)

    assert portal.call(listed) == (33, TriageVerdict.SKIP, "Onsite Berlin")


def test_the_list_orders_by_verdict_then_score_then_age_with_text_less_last(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    rows = {
        "waiting": portal.call(_add, uow, ALICE, None, NOW + timedelta(minutes=9)),
        "plain_new": portal.call(_add, uow, ALICE, "p2", NOW + timedelta(minutes=8)),
        "plain_old": portal.call(_add, uow, ALICE, "p1", NOW + timedelta(minutes=1)),
        "skip": portal.call(_add, uow, ALICE, "s", NOW + timedelta(minutes=2)),
        "maybe": portal.call(_add, uow, ALICE, "m", NOW + timedelta(minutes=3)),
        "analyse_low": portal.call(_add, uow, ALICE, "a1", NOW + timedelta(minutes=4)),
        "analyse_high": portal.call(_add, uow, ALICE, "a2", NOW + timedelta(minutes=5)),
    }
    for name, score, verdict in (
        ("skip", 99, TriageVerdict.SKIP),
        ("maybe", 10, TriageVerdict.MAYBE),
        ("analyse_low", 61, TriageVerdict.ANALYSE),
        ("analyse_high", 88, TriageVerdict.ANALYSE),
    ):
        portal.call(_save, uow, ALICE, rows[name], score, verdict)

    async def listed(search: JobSearch | None = None) -> list[int]:
        async with uow() as tx:
            found = await tx.jobs.search(ALICE, search or JobSearch())
            return [item.number for item in found]

    expected = [
        rows[name][0]
        for name in (
            "analyse_high",
            "analyse_low",
            "maybe",
            "skip",
            "plain_new",
            "plain_old",
            "waiting",
        )
    ]
    assert portal.call(listed) == expected
    assert portal.call(listed, JobSearch(triage_verdict=TriageVerdict.MAYBE)) == [
        rows["maybe"][0]
    ]


def test_the_details_triage_is_read_through_the_jobs_port(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    portal.call(_save, uow, ALICE, job, 55, TriageVerdict.MAYBE, "Short", NOW)

    async def read(user: UserId) -> Triage | None:
        async with uow() as tx:
            return await tx.jobs.get_triage(user, job[0])

    triage = portal.call(read, ALICE)
    assert triage is not None
    assert (triage.score, triage.verdict, triage.reason, triage.triaged_at) == (
        55,
        TriageVerdict.MAYBE,
        "Short",
        NOW,
    )
    assert portal.call(read, BOB) is None


def test_the_schema_rejects_a_score_or_verdict_outside_the_rules(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE, "job")

    async def insert(score: int, verdict: str) -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO job_triage"
                    " (id, user_id, job_id, score, verdict, reason, triaged_at)"
                    " SELECT gen_random_uuid(), user_id, id, :score, :verdict, 'r', now()"
                    " FROM jobs"
                ),
                {"score": score, "verdict": verdict},
            )

    with pytest.raises(IntegrityError, match="score"):
        portal.call(insert, 101, "maybe")
    with pytest.raises(IntegrityError, match="verdict"):
        portal.call(insert, 50, "great")
    assert portal.call(_scalar, engine, "SELECT count(*) FROM job_triage") == 0


def test_the_table_has_every_v1_column_for_the_etl(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    columns = portal.call(
        _scalar,
        engine,
        "SELECT array_agg(column_name::text) FROM information_schema.columns"
        " WHERE table_name = 'job_triage'",
    )
    assert set(columns) >= V1_TRIAGE_COLUMNS  # type: ignore[call-overload]


def test_removing_a_job_or_a_user_removes_its_triage(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    mine = portal.call(_add, uow, ALICE, "a")
    theirs = portal.call(_add, uow, BOB, "b")
    portal.call(_save, uow, ALICE, mine)
    portal.call(_save, uow, BOB, theirs)

    async def run(sql: str, params: Mapping[str, object]) -> None:
        async with engine.begin() as conn:
            await conn.execute(text(sql), params)

    portal.call(
        run,
        "DELETE FROM jobs WHERE job_number = :n AND user_id = :u",
        {"n": mine[0], "u": ALICE.value},
    )
    assert portal.call(_scalar, engine, "SELECT count(*) FROM job_triage") == 1
    portal.call(run, "DELETE FROM users WHERE id = :u", {"u": BOB.value})
    assert portal.call(_scalar, engine, "SELECT count(*) FROM job_triage") == 0


def test_a_job_without_text_is_neither_a_candidate_nor_pending(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, None)
    assert portal.call(_candidates, uow, ALICE) == []
    assert portal.call(_pending, uow, ALICE) == 0


def test_an_analysed_job_is_neither_a_candidate_nor_pending(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_add, uow, ALICE, "analysed")

    async def analyse() -> None:
        async with uow() as tx:
            await tx.analyses.save(
                ALICE,
                AnalysisId(_id()),
                job[1],
                JobAnalysis(score=70, summary="S."),
                (),
                NOW,
            )
            await tx.commit()

    portal.call(analyse)
    assert portal.call(_candidates, uow, ALICE) == []
    assert portal.call(_pending, uow, ALICE) == 0


def test_a_dismissed_job_is_neither_a_candidate_nor_pending(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_add, uow, ALICE, "dismissed")

    async def hide() -> None:
        async with uow() as tx:
            await tx.jobs.dismiss(ALICE, [job[0]], "r", NOW)
            await tx.commit()

    portal.call(hide)
    assert portal.call(_candidates, uow, ALICE) == []
    assert portal.call(_pending, uow, ALICE) == 0


@pytest.mark.parametrize(
    "status", [ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN]
)
def test_a_job_with_a_closed_application_is_neither_a_candidate_nor_pending(
    portal: BlockingPortal, uow: UnitOfWorkFactory, status: ApplicationStatus
) -> None:
    closed = portal.call(_add, uow, ALICE, "closed")
    kept = portal.call(_add, uow, ALICE, "kept")
    portal.call(_apply, uow, ALICE, closed[0], status)
    assert portal.call(_candidates, uow, ALICE) == [kept[0]]
    assert portal.call(_pending, uow, ALICE) == 1


@pytest.mark.parametrize(
    "status",
    [
        ApplicationStatus.APPLIED,
        ApplicationStatus.REPLIED,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.OFFER,
    ],
)
def test_a_job_with_an_active_application_stays_a_candidate(
    portal: BlockingPortal, uow: UnitOfWorkFactory, status: ApplicationStatus
) -> None:
    active = portal.call(_add, uow, ALICE, "active")
    portal.call(_apply, uow, ALICE, active[0], status)
    assert portal.call(_candidates, uow, ALICE) == [active[0]]
    assert portal.call(_pending, uow, ALICE) == 1


def test_the_closed_application_of_another_user_hides_nothing(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    mine = portal.call(_add, uow, ALICE, "mine")
    theirs = portal.call(_add, uow, BOB, "theirs")
    portal.call(_apply, uow, BOB, theirs[0], ApplicationStatus.REJECTED)
    assert portal.call(_candidates, uow, ALICE) == [mine[0]]
    assert portal.call(_pending, uow, ALICE) == 1
