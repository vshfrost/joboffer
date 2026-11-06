"""PostgresAnalyses, список з аналізом і час зміни профілю на справжній базі."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.analysis.analysis import Analysis, Gap, JobAnalysis
from domain.analysis.ids import AnalysisId
from domain.analysis.keywords import KeywordFacts
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.search import JobSearch
from domain.profile.modes import Seniority, WorkMode
from domain.triage.ids import TriageId
from domain.triage.triage import TriageEntry, TriageVerdict
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, posting, uow

__all__ = ["uow"]

_ids = iter(range(1, 10_000))


def _id() -> UUID:
    return UUID(int=0xC000 + next(_ids))


# Усі колонки `job_analyses` v1: ETL у B12 переносить їх без втрат.
V1_ANALYSIS_COLUMNS = {
    "score",
    "work_mode",
    "filters_passed",
    "flags",
    "details",
    "updated_at",
}

FULL = JobAnalysis(
    score=77,
    summary="A backend role.",
    must_have=("Python", "Postgres"),
    nice_to_have=("Go",),
    keywords=("asyncio",),
    seniority=Seniority.SENIOR,
    work_mode=WorkMode.REMOTE,
    location="Madrid",
    languages=("English",),
    salary_min_eur=60000,
    salary_max_eur=80000,
    relocation=False,
    reasons=("Fits",),
    gaps=(Gap("No Go", "Do you have Go experience? Where, how long?"),),
    candidate_asks=("Send your GitHub", "Skip the list of frameworks"),
)


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


async def _analyse(
    uow: UnitOfWorkFactory,
    user: UserId,
    job: tuple[int, JobId],
    analysis: JobAnalysis = FULL,
    flags: tuple[str, ...] = (),
    now: datetime = NOW,
) -> None:
    async with uow() as tx:
        await tx.analyses.save(user, AnalysisId(_id()), job[1], analysis, flags, now)
        await tx.commit()


async def _get(
    uow: UnitOfWorkFactory, user: UserId, job: tuple[int, JobId]
) -> Analysis | None:
    async with uow() as tx:
        return await tx.analyses.get(user, job[1])


async def _execute(engine: AsyncEngine, sql: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql))


async def _scalar(engine: AsyncEngine, sql: str) -> object:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar()


def test_an_unanalysed_job_has_no_analysis(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    assert portal.call(_get, uow, ALICE, job) is None


def test_a_saved_analysis_reads_back_whole(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    flags = ("Формат remote — не з профілю.", "Стоп-слово: crypto.")
    portal.call(_analyse, uow, ALICE, job, FULL, flags, NOW)
    saved = portal.call(_get, uow, ALICE, job)
    assert saved == Analysis(job[0], FULL, flags, NOW)
    assert saved is not None
    assert saved.filters_passed is False


def test_gaps_keep_their_order_and_questions_and_old_ones_have_none(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    gaps = (Gap("Kubernetes", "Have you run it? Where?"), Gap("Go", None))
    portal.call(_analyse, uow, ALICE, job, JobAnalysis(5, "s", gaps=gaps))
    saved = portal.call(_get, uow, ALICE, job)
    assert saved is not None
    assert saved.analysis.gaps == gaps


def test_the_fact_map_keeps_its_order_and_an_old_row_without_it_reads_none(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    mapped = JobAnalysis(
        5,
        "s",
        keywords=("Python", "Kafka | Rabbit"),
        keyword_facts=(
            KeywordFacts("Python", (3, 1)),
            KeywordFacts("Kafka | Rabbit", ()),
        ),
    )
    portal.call(_analyse, uow, ALICE, job, mapped)
    saved = portal.call(_get, uow, ALICE, job)
    assert saved is not None
    assert saved.analysis.keyword_facts == mapped.keyword_facts

    portal.call(
        _execute, engine, "UPDATE job_analyses SET details = details - 'keyword_facts'"
    )
    old = portal.call(_get, uow, ALICE, job)
    assert old is not None
    assert old.analysis.keyword_facts is None


def test_candidate_asks_keep_their_order_and_an_old_row_without_them_reads_empty(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    asks = ("Tell us about one time AI got in your way", "Send your GitHub")
    portal.call(_analyse, uow, ALICE, job, JobAnalysis(5, "s", candidate_asks=asks))
    saved = portal.call(_get, uow, ALICE, job)
    assert saved is not None
    assert saved.analysis.candidate_asks == asks

    portal.call(
        _execute,
        engine,
        "UPDATE job_analyses SET details = details - 'candidate_asks'",
    )
    old = portal.call(_get, uow, ALICE, job)
    assert old is not None
    assert old.analysis.candidate_asks == ()


def test_an_analysis_stored_with_string_gaps_reads_with_null_questions(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    portal.call(_analyse, uow, ALICE, job, JobAnalysis(5, "s"))
    portal.call(
        _execute,
        engine,
        "UPDATE job_analyses SET details = jsonb_set(details, '{gaps}', "
        """'["Old gap", "Another"]'::jsonb)""",
    )
    saved = portal.call(_get, uow, ALICE, job)
    assert saved is not None
    assert saved.analysis.gaps == (Gap("Old gap", None), Gap("Another", None))


def test_an_analysis_with_nothing_stated_reads_back_with_empties(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    bare = JobAnalysis(score=0, summary="Thin posting.")
    portal.call(_analyse, uow, ALICE, job, bare)
    saved = portal.call(_get, uow, ALICE, job)
    assert saved is not None
    assert saved.analysis == bare
    assert saved.filters_passed is True


def test_a_repeated_save_replaces_the_row_and_keeps_the_first_id(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    portal.call(_analyse, uow, ALICE, job, JobAnalysis(10, "First."), ("f",), NOW)
    first_id = portal.call(_scalar, engine, "SELECT id FROM job_analyses")
    later = NOW + timedelta(days=1)
    portal.call(_analyse, uow, ALICE, job, JobAnalysis(90, "Second."), (), later)

    assert portal.call(_scalar, engine, "SELECT count(*) FROM job_analyses") == 1
    assert portal.call(_scalar, engine, "SELECT id FROM job_analyses") == first_id
    saved = portal.call(_get, uow, ALICE, job)
    assert saved == Analysis(job[0], JobAnalysis(90, "Second."), (), later)


def test_a_user_does_not_see_the_analysis_of_another(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    mine = portal.call(_add, uow, ALICE, "job")
    portal.call(_analyse, uow, ALICE, mine)
    assert portal.call(_get, uow, BOB, mine) is None


def test_the_columns_for_sorting_and_filtering_are_filled(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    portal.call(_analyse, uow, ALICE, job, FULL, ("f",))
    row = portal.call(
        _scalar,
        engine,
        "SELECT concat_ws('|', score, work_mode, filters_passed) FROM job_analyses",
    )
    assert row == "77|remote|f"


def test_the_schema_rejects_a_score_outside_0_to_100(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE, "job")

    async def insert(score: int) -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO job_analyses (id, user_id, job_id, score, filters_passed,"
                    " flags, details, updated_at)"
                    " SELECT gen_random_uuid(), user_id, id, :score, true, '{}', '{}', now()"
                    " FROM jobs"
                ),
                {"score": score},
            )

    with pytest.raises(IntegrityError, match="score"):
        portal.call(insert, 101)
    with pytest.raises(IntegrityError, match="score"):
        portal.call(insert, -1)


def test_the_table_has_every_v1_column_for_the_etl(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    columns = portal.call(
        _scalar,
        engine,
        "SELECT array_agg(column_name::text) FROM information_schema.columns"
        " WHERE table_name = 'job_analyses'",
    )
    assert set(columns) >= V1_ANALYSIS_COLUMNS  # type: ignore[call-overload]


def test_removing_a_job_or_a_user_removes_its_analysis(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    mine = portal.call(_add, uow, ALICE, "a")
    theirs = portal.call(_add, uow, BOB, "b")
    portal.call(_analyse, uow, ALICE, mine)
    portal.call(_analyse, uow, BOB, theirs)

    async def run(sql: str, params: Mapping[str, object]) -> None:
        async with engine.begin() as conn:
            await conn.execute(text(sql), params)

    portal.call(
        run,
        "DELETE FROM jobs WHERE job_number = :n AND user_id = :u",
        {"n": mine[0], "u": ALICE.value},
    )
    assert portal.call(_scalar, engine, "SELECT count(*) FROM job_analyses") == 1
    portal.call(run, "DELETE FROM users WHERE id = :u", {"u": BOB.value})
    assert portal.call(_scalar, engine, "SELECT count(*) FROM job_analyses") == 0


# --- список ------------------------------------------------------------------------


def test_the_list_shows_score_filters_and_work_mode(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    portal.call(_analyse, uow, ALICE, job, FULL, ("f",))

    async def listed() -> tuple[object, ...]:
        async with uow() as tx:
            [item] = await tx.jobs.search(ALICE, JobSearch())
            return (item.score, item.filters_passed, item.work_mode)

    assert portal.call(listed) == (77, False, WorkMode.REMOTE)


def test_the_list_follows_the_v1_order_over_every_state(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    def at(minutes: int) -> datetime:
        return NOW + timedelta(minutes=minutes)

    rows = {
        "waiting": portal.call(_add, uow, ALICE, None, at(9)),
        "plain_new": portal.call(_add, uow, ALICE, "p2", at(8)),
        "plain_old": portal.call(_add, uow, ALICE, "p1", at(1)),
        "skip": portal.call(_add, uow, ALICE, "s", at(2)),
        "maybe_low": portal.call(_add, uow, ALICE, "m1", at(3)),
        "maybe_high": portal.call(_add, uow, ALICE, "m2", at(4)),
        "analyse": portal.call(_add, uow, ALICE, "a", at(5)),
        "failed_high": portal.call(_add, uow, ALICE, "f", at(6)),
        "passed_low": portal.call(_add, uow, ALICE, "pl", at(7)),
        "passed_high": portal.call(_add, uow, ALICE, "ph", at(7)),
    }

    async def triage(name: str, score: int, verdict: TriageVerdict) -> None:
        number, job_id = rows[name]
        async with uow() as tx:
            await tx.triage.save(
                ALICE,
                [(TriageId(_id()), job_id, TriageEntry(number, score, verdict, "r"))],
                NOW,
            )
            await tx.commit()

    for name, score, verdict in (
        ("skip", 99, TriageVerdict.SKIP),
        ("maybe_low", 10, TriageVerdict.MAYBE),
        ("maybe_high", 70, TriageVerdict.MAYBE),
        ("analyse", 1, TriageVerdict.ANALYSE),
    ):
        portal.call(triage, name, score, verdict)
    portal.call(_analyse, uow, ALICE, rows["passed_low"], JobAnalysis(40, "s"))
    portal.call(_analyse, uow, ALICE, rows["passed_high"], JobAnalysis(85, "s"))
    portal.call(_analyse, uow, ALICE, rows["failed_high"], JobAnalysis(99, "s"), ("f",))

    async def listed(search: JobSearch | None = None) -> list[int]:
        async with uow() as tx:
            return [
                i.number for i in await tx.jobs.search(ALICE, search or JobSearch())
            ]

    order = (
        "passed_high",
        "passed_low",
        "failed_high",
        "analyse",
        "maybe_high",
        "maybe_low",
        "skip",
        "plain_new",
        "plain_old",
        "waiting",
    )
    assert portal.call(listed) == [rows[name][0] for name in order]


def test_the_work_mode_filter_keeps_only_analysed_jobs_of_that_mode(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    remote = portal.call(_add, uow, ALICE, "r")
    onsite = portal.call(_add, uow, ALICE, "o")
    portal.call(_add, uow, ALICE, "plain")
    portal.call(
        _analyse, uow, ALICE, remote, JobAnalysis(1, "s", work_mode=WorkMode.REMOTE)
    )
    portal.call(
        _analyse, uow, ALICE, onsite, JobAnalysis(1, "s", work_mode=WorkMode.ONSITE)
    )

    async def listed(mode: WorkMode) -> list[int]:
        async with uow() as tx:
            found = await tx.jobs.search(ALICE, JobSearch(work_mode=mode))
            return [item.number for item in found]

    assert portal.call(listed, WorkMode.REMOTE) == [remote[0]]
    assert portal.call(listed, WorkMode.HYBRID) == []


# --- triage і аналіз ------------------------------------------------------------------


def test_an_analysed_job_is_not_a_triage_candidate(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    analysed = portal.call(_add, uow, ALICE, "a", NOW)
    waiting = portal.call(_add, uow, ALICE, "b", NOW + timedelta(minutes=1))
    portal.call(_analyse, uow, ALICE, analysed)

    async def candidates() -> tuple[list[int], int]:
        async with uow() as tx:
            jobs = await tx.triage.candidates(ALICE, 20)
            return [job.number for job in jobs], await tx.triage.pending(ALICE)

    assert portal.call(candidates) == ([waiting[0]], 1)


# --- час зміни профілю ---------------------------------------------------------------------


def test_the_profile_has_no_change_time_until_a_change_is_marked(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def read(user: UserId) -> datetime | None:
        async with uow() as tx:
            return await tx.profiles.analysis_inputs_changed_at(user)

    assert portal.call(read, ALICE) is None


def test_marking_a_change_stores_its_time_for_that_user_only(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def mark(user: UserId, when: datetime) -> None:
        async with uow() as tx:
            await tx.profiles.mark_analysis_inputs_changed(user, when)
            await tx.commit()

    async def read(user: UserId) -> datetime | None:
        async with uow() as tx:
            return await tx.profiles.analysis_inputs_changed_at(user)

    later = NOW + timedelta(hours=3)
    portal.call(mark, ALICE, NOW)
    portal.call(mark, ALICE, later)
    assert portal.call(read, ALICE) == later
    assert portal.call(read, BOB) is None
