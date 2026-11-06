"""Тріаж за правилами на справжній базі: кандидати (нові й застарілі), `agent` недоторканний, лок,
користувачі з роботою, скори аналізів, міграція 0033, прогін use case-у."""

from datetime import timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from application.triage.auto import AutoTriageUseCases
from domain.analysis.analysis import JobAnalysis
from domain.analysis.ids import AnalysisId
from domain.applications.application import ApplicationStatus
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.triage import scoring
from domain.triage.ids import TriageId
from domain.triage.scoring import inputs_hash
from domain.triage.triage import TriageEntry, TriageVerdict
from infrastructure.db.engine import create_engine
from infrastructure.db.migrate import upgrade
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, uow
from tests.integration.test_triage_repository import _add, _apply, _id, _save
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds

__all__ = ["uow"]

CONTEXT = "context-digest"
LATER = NOW + timedelta(days=1)
Job = tuple[int, JobId]


async def _add_full(
    uow: UnitOfWorkFactory,
    user: UserId,
    body: str | None,
    title: str | None,
    location: str | None,
    when: Any = NOW,
) -> Job:
    job_id = JobId(_id())
    async with uow() as tx:
        number = await tx.jobs.add(
            user,
            job_id,
            NewJob(
                text=body,
                title=title,
                company="Acme",
                location=location,
            ),
            when,
        )
        await tx.commit()
    return number, job_id


async def _auto_save(
    uow: UnitOfWorkFactory,
    user: UserId,
    job: Job,
    context: str = CONTEXT,
    score: int = 70,
    reason: str = "auto",
    now: Any = NOW,
) -> None:
    number, job_id = job
    async with uow() as tx:
        stored = await tx.jobs.get(user, number)
        assert stored is not None
        entry = TriageEntry(number, score, TriageVerdict.MAYBE, reason)
        await tx.triage.save_auto(
            user,
            [(TriageId(_id()), job_id, entry, inputs_hash(context, stored))],
            now,
        )
        await tx.commit()


async def _auto(
    uow: UnitOfWorkFactory, user: UserId, context: str = CONTEXT, limit: int = 200
) -> list[int]:
    async with uow() as tx:
        return [
            job.number for job in await tx.triage.auto_candidates(user, context, limit)
        ]


async def _work(uow: UnitOfWorkFactory) -> list[UserId]:
    async with uow() as tx:
        return await tx.triage.users_with_work()


async def _rows(engine: AsyncEngine, sql: str) -> list[tuple[Any, ...]]:
    async with engine.connect() as conn:
        return [tuple(row) for row in (await conn.execute(text(sql))).all()]


def test_untriaged_jobs_are_auto_candidates_newest_first_up_to_the_limit(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    for index in range(3):
        portal.call(_add, uow, ALICE, f"job {index}", NOW + timedelta(minutes=index))
    portal.call(_add, uow, BOB, "bobs")

    assert portal.call(_auto, uow, ALICE) == [3, 2, 1]
    assert portal.call(_auto, uow, ALICE, CONTEXT, 2) == [3, 2]


def test_a_rules_triage_with_matching_inputs_is_not_a_candidate(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    """Те саме для вакансій з порожніми полями й не-ASCII: хеш у SQL збігається з `inputs_hash`."""
    jobs = [
        portal.call(
            _add_full, uow, ALICE, "Requirements:\nPython", "Engineer", "Madrid"
        ),
        portal.call(_add_full, uow, ALICE, "Вакансія: розробник ✓ café", None, None),
        portal.call(_add_full, uow, ALICE, "text", "Інженер", "Валенсія"),
    ]
    for job in jobs:
        portal.call(_auto_save, uow, ALICE, job)

    assert portal.call(_auto, uow, ALICE) == []


def test_a_rules_triage_is_a_candidate_again_when_the_context_changes(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_add_full, uow, ALICE, "text", "Engineer", "Madrid")
    portal.call(_auto_save, uow, ALICE, job)

    assert portal.call(_auto, uow, ALICE, "another-context") == [job[0]]


def test_a_rules_triage_is_a_candidate_again_when_the_rules_version_changes(
    portal: BlockingPortal, uow: UnitOfWorkFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = portal.call(_add_full, uow, ALICE, "text", "Engineer", "Madrid")
    portal.call(_auto_save, uow, ALICE, job)
    assert portal.call(_auto, uow, ALICE) == []

    monkeypatch.setattr(scoring, "RULES_VERSION", scoring.RULES_VERSION + 1)

    assert portal.call(_auto, uow, ALICE) == [job[0]]


def test_the_sql_hash_agrees_with_the_python_hash_under_another_rules_version(
    portal: BlockingPortal, uow: UnitOfWorkFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scoring, "RULES_VERSION", 7)
    jobs = [
        portal.call(_add_full, uow, ALICE, "Вакансія ✓ café", None, None),
        portal.call(_add_full, uow, ALICE, "text", "Engineer", "Madrid"),
    ]
    for job in jobs:
        portal.call(_auto_save, uow, ALICE, job)

    assert portal.call(_auto, uow, ALICE) == []


def test_a_rules_version_change_never_makes_an_agent_triage_a_candidate(
    portal: BlockingPortal, uow: UnitOfWorkFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = portal.call(_add, uow, ALICE, "text")
    portal.call(_save, uow, ALICE, job, 70, TriageVerdict.ANALYSE, "agent")

    monkeypatch.setattr(scoring, "RULES_VERSION", scoring.RULES_VERSION + 1)

    assert portal.call(_auto, uow, ALICE) == []


@pytest.mark.parametrize(
    "update",
    [
        "UPDATE jobs SET text = 'new text'",
        "UPDATE jobs SET title = 'New title'",
        "UPDATE jobs SET location = 'Berlin'",
    ],
)
def test_a_rules_triage_is_a_candidate_again_when_the_job_changes(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine, update: str
) -> None:
    job = portal.call(_add_full, uow, ALICE, "text", "Engineer", "Madrid")
    portal.call(_auto_save, uow, ALICE, job)

    async def edit() -> None:
        async with engine.begin() as conn:
            await conn.execute(text(update))

    portal.call(edit)
    assert portal.call(_auto, uow, ALICE) == [job[0]]


def test_an_agent_triage_is_never_an_auto_candidate(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_add, uow, ALICE, "text")
    portal.call(_save, uow, ALICE, job)

    assert portal.call(_auto, uow, ALICE) == []
    assert portal.call(_auto, uow, ALICE, "another-context") == []


def test_jobs_outside_the_candidate_rule_are_not_auto_candidates(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    kept = portal.call(_add, uow, ALICE, "kept")
    analysed = portal.call(_add, uow, ALICE, "analysed")
    hidden = portal.call(_add, uow, ALICE, "hidden")
    closed = portal.call(_add, uow, ALICE, "closed")
    portal.call(_add, uow, ALICE, None)

    async def prepare() -> None:
        async with uow() as tx:
            await tx.analyses.save(
                ALICE,
                AnalysisId(_id()),
                analysed[1],
                JobAnalysis(score=70, summary="S."),
                (),
                NOW,
            )
            await tx.jobs.dismiss(ALICE, [hidden[0]], "r", NOW)
            await tx.commit()

    portal.call(prepare)
    portal.call(_apply, uow, ALICE, closed[0], ApplicationStatus.WITHDRAWN)

    assert portal.call(_auto, uow, ALICE) == [kept[0]]


def test_save_auto_stores_the_rules_row_with_its_hash(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_add_full, uow, ALICE, "text", "Engineer", "Madrid")
    portal.call(_auto_save, uow, ALICE, job, CONTEXT, 55, "Невпевнено", LATER)

    async def stored_hash() -> str:
        async with uow() as tx:
            found = await tx.jobs.get(ALICE, job[0])
            assert found is not None
            return inputs_hash(CONTEXT, found)

    rows = portal.call(
        _rows,
        engine,
        "SELECT source, score, verdict, reason, triaged_at, inputs_hash FROM job_triage",
    )
    assert rows == [
        ("rules", 55, "maybe", "Невпевнено", LATER, portal.call(stored_hash))
    ]


def test_save_auto_recalculates_a_rules_row_and_keeps_its_id(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_add, uow, ALICE, "text")
    portal.call(_auto_save, uow, ALICE, job, "old", 20, "first", NOW)
    first = portal.call(_rows, engine, "SELECT id FROM job_triage")
    portal.call(_auto_save, uow, ALICE, job, "new", 80, "second", LATER)

    rows = portal.call(
        _rows, engine, "SELECT id, source, score, reason, triaged_at FROM job_triage"
    )
    assert rows == [(first[0][0], "rules", 80, "second", LATER)]
    assert portal.call(_auto, uow, ALICE, "new") == []


def test_save_auto_never_overwrites_an_agent_row(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_add, uow, ALICE, "text")
    portal.call(_save, uow, ALICE, job, 90, TriageVerdict.ANALYSE, "Claude", NOW)
    portal.call(_auto_save, uow, ALICE, job, CONTEXT, 10, "auto", LATER)

    rows = portal.call(
        _rows,
        engine,
        "SELECT source, score, verdict, reason, triaged_at, inputs_hash FROM job_triage",
    )
    assert rows == [("agent", 90, "analyse", "Claude", NOW, None)]


def test_an_agent_save_marks_the_row_agent_and_replaces_a_rules_row(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_add, uow, ALICE, "text")
    portal.call(_auto_save, uow, ALICE, job, CONTEXT, 10, "auto", NOW)
    portal.call(_save, uow, ALICE, job, 90, TriageVerdict.ANALYSE, "Claude", LATER)

    rows = portal.call(
        _rows,
        engine,
        "SELECT source, score, reason, inputs_hash FROM job_triage",
    )
    assert rows == [("agent", 90, "Claude", None)]
    assert portal.call(_auto, uow, ALICE, "another-context") == []


def test_users_with_work_have_an_untriaged_or_rules_triaged_candidate(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    assert portal.call(_work, uow) == []
    alice = portal.call(_add, uow, ALICE, "a")
    bob = portal.call(_add, uow, BOB, "b")
    assert portal.call(_work, uow) == [ALICE, BOB]

    portal.call(_save, uow, BOB, bob)
    assert portal.call(_work, uow) == [ALICE]
    portal.call(_auto_save, uow, ALICE, alice)
    assert portal.call(_work, uow) == [ALICE]


def test_users_with_work_ignore_jobs_outside_the_candidate_rule(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, None)
    portal.call(
        _apply,
        uow,
        BOB,
        portal.call(_add, uow, BOB, "closed")[0],
        ApplicationStatus.REJECTED,
    )

    assert portal.call(_work, uow) == []


def test_users_with_jobs_have_a_job_with_text(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def users() -> list[UserId]:
        async with uow() as tx:
            return await tx.triage.users_with_jobs()

    portal.call(_add, uow, ALICE, None)
    assert portal.call(users) == []
    portal.call(_add, uow, BOB, "text")
    assert portal.call(users) == [BOB]


def test_analysed_scores_pair_each_analysed_job_with_its_score(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_add, uow, ALICE, "first")
    portal.call(_add, uow, ALICE, "plain")
    other = portal.call(_add, uow, BOB, "bobs")

    async def analyse() -> None:
        async with uow() as tx:
            for user, job, score in ((ALICE, first, 81), (BOB, other, 12)):
                await tx.analyses.save(
                    user,
                    AnalysisId(_id()),
                    job[1],
                    JobAnalysis(score=score, summary="S."),
                    (),
                    NOW,
                )
            await tx.commit()

    async def scores() -> list[tuple[int, int]]:
        async with uow() as tx:
            return [
                (job.number, score)
                for job, score in await tx.triage.analysed_scores(ALICE)
            ]

    portal.call(analyse)
    assert portal.call(scores) == [(first[0], 81)]


def test_only_one_transaction_holds_the_run_lock(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def contend() -> tuple[bool, bool, bool]:
        async with uow() as first:
            held = await first.triage.lock()
            async with uow() as second:
                blocked = await second.triage.lock()
        async with uow() as third:
            released = await third.triage.lock()
        return held, blocked, released

    assert portal.call(contend) == (True, False, True)


def test_the_migration_marks_existing_triage_as_agent_without_a_hash(
    portal: BlockingPortal, scratch_url: str
) -> None:
    user = "00000000-0000-0000-0000-0000000000a1"
    job = "00000000-0000-0000-0000-0000000000b1"

    async def run() -> list[tuple[Any, ...]]:
        scratch = create_engine(scratch_url)
        try:
            await upgrade(scratch, "0032")
            async with scratch.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, password_hash, "
                        "version, created_at) "
                        "VALUES (:u, 'a@example.com', 'U', 'x', 1, now())"
                    ),
                    {"u": user},
                )
                await conn.execute(
                    text(
                        "INSERT INTO jobs (id, user_id, job_number, source, text, created_at) "
                        "VALUES (:j, :u, 1, 'manual', 't', now())"
                    ),
                    {"j": job, "u": user},
                )
                await conn.execute(
                    text(
                        "INSERT INTO job_triage (id, user_id, job_id, score, verdict, "
                        "reason, triaged_at) VALUES (gen_random_uuid(), :u, :j, 50, "
                        "'maybe', 'r', now())"
                    ),
                    {"j": job, "u": user},
                )
            await upgrade(scratch)
            async with scratch.connect() as conn:
                found = await conn.execute(
                    text("SELECT source, inputs_hash FROM job_triage")
                )
                return [tuple(row) for row in found.all()]
        finally:
            await scratch.dispose()

    assert portal.call(run) == [("agent", None)]


def test_the_schema_rejects_an_unknown_triage_source(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE, "job")

    async def insert() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO job_triage"
                    " (id, user_id, job_id, score, verdict, reason, triaged_at, source)"
                    " SELECT gen_random_uuid(), user_id, id, 50, 'maybe', 'r', now(), 'llm'"
                    " FROM jobs"
                )
            )

    with pytest.raises(IntegrityError, match="source"):
        portal.call(insert)


def test_a_full_run_triages_every_user_once_and_leaves_agent_rows(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE, "Requirements:\nPython\nDocker\nKafka")
    portal.call(_add, uow, BOB, "Great job.")
    kept = portal.call(_add, uow, BOB, "Claude saw this")
    portal.call(_save, uow, BOB, kept, 99, TriageVerdict.ANALYSE, "Claude", NOW)
    auto = AutoTriageUseCases(uow, FakeClock(LATER), SequentialIds(7000))

    first = portal.call(auto.run)
    second = portal.call(auto.run)

    assert (first.users, first.triaged, first.failures) == (2, 2, [])
    assert (second.users, second.triaged) == (2, 0)
    rows = portal.call(
        _rows,
        engine,
        "SELECT j.job_number, t.source, t.score, t.verdict, t.triaged_at"
        " FROM job_triage t JOIN jobs j ON j.id = t.job_id ORDER BY t.user_id, j.job_number",
    )
    assert rows == [
        (1, "rules", 30, "skip", LATER),
        (1, "rules", 50, "maybe", LATER),
        (2, "agent", 99, "analyse", NOW),
    ]
