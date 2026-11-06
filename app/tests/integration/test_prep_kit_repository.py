"""PostgresInterviewKits на справжній базі: версії окремо для кожної вакансії, номери на
користувача, вміст у формі v1, схема для ETL."""

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.prep.ids import KitId
from domain.prep.kit import (
    InterviewKit,
    KitQuestion,
    KitQuestionKind,
    KitVersion,
    StarStory,
)
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW
from tests.integration.test_prep_repository import _id, _job, _run, uow

__all__ = ["uow"]

LATER = NOW + timedelta(days=2)


def _kit(tag: str = "a", *, topic: int | None = None) -> InterviewKit:
    return InterviewKit(
        questions=tuple(
            KitQuestion(
                KitQuestionKind.TECHNICAL if n % 2 else KitQuestionKind.BEHAVIORAL,
                f"Question {tag}{n}?",
                topic if n == 1 else None,
            )
            for n in range(1, 6)
        ),
        stories=tuple(
            StarStory(
                f"Story {tag}{n}",
                f"Situation {n}",
                f"Task {n}",
                f"Action {n}",
                f"Result {n}",
                (n, n + 10),
            )
            for n in range(1, 4)
        ),
        company_questions=tuple(f"Ask {tag}{n}?" for n in range(1, 4)),
    )


async def _add(
    uow: UnitOfWorkFactory,
    user: UserId,
    job: JobId,
    kit: InterviewKit | None = None,
    at: Any = NOW,
) -> KitVersion:
    async with uow() as tx:
        saved = await tx.interview_kits.add(user, KitId(_id()), job, kit or _kit(), at)
        await tx.commit()
        return saved


async def _latest(
    uow: UnitOfWorkFactory, user: UserId, job: JobId
) -> KitVersion | None:
    async with uow() as tx:
        return await tx.interview_kits.latest(user, job)


def _must(version: KitVersion | None) -> KitVersion:
    assert version is not None, "пакета нема"
    return version


def test_a_new_version_reads_back_whole_with_the_number_of_its_job(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_job, uow, ALICE, "Перша")
    job = portal.call(_job, uow, ALICE, "Друга")
    kit = _kit("a", topic=4)
    kit_id = KitId(_id())

    async def add() -> KitVersion:
        async with uow() as tx:
            saved = await tx.interview_kits.add(ALICE, kit_id, job, kit, NOW)
            await tx.commit()
            return saved

    added = portal.call(add)

    expected = KitVersion(
        id=kit_id, number=1, job_number=2, version=1, kit=kit, created_at=NOW
    )
    assert added == expected
    assert portal.call(_latest, uow, ALICE, job) == expected


def test_the_order_topics_facts_and_unicode_survive_the_round_trip(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE, "A")
    kit = InterviewKit(
        questions=tuple(
            KitQuestion(KitQuestionKind.BEHAVIORAL, f"Питання {n}?", n % 3 or None)
            for n in range(5, 0, -1)
        ),
        stories=tuple(
            StarStory("Історія", "S", "T", "A", "R", (9, 3, 7)) for _ in range(3)
        ),
        company_questions=("Чи є хаб у Валенсії?", "Z?", "A?"),
    )

    portal.call(_add, uow, ALICE, job, kit)

    assert _must(portal.call(_latest, uow, ALICE, job)).kit == kit


def test_versions_count_per_job_and_the_latest_is_the_newest(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_job, uow, ALICE, "A")
    second = portal.call(_job, uow, ALICE, "B")

    portal.call(_add, uow, ALICE, first, _kit("one"))
    portal.call(_add, uow, ALICE, first, _kit("two"), LATER)
    other = portal.call(_add, uow, ALICE, second, _kit("other"))

    newest = _must(portal.call(_latest, uow, ALICE, first))
    assert (newest.version, newest.kit, newest.created_at) == (2, _kit("two"), LATER)
    assert (other.version, other.job_number) == (1, 2)


def test_numbers_run_across_the_jobs_of_a_user_and_restart_for_another_user(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_job, uow, ALICE, "A")
    second = portal.call(_job, uow, ALICE, "B")
    bobs = portal.call(_job, uow, BOB, "C")

    numbers = [
        portal.call(_add, uow, ALICE, first).number,
        portal.call(_add, uow, ALICE, second).number,
        portal.call(_add, uow, ALICE, first).number,
        portal.call(_add, uow, BOB, bobs).number,
    ]

    assert numbers == [1, 2, 3, 1]


def test_a_job_without_a_kit_has_no_latest_version(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE, "A")
    other = portal.call(_job, uow, ALICE, "B")
    portal.call(_add, uow, ALICE, other)

    assert portal.call(_latest, uow, ALICE, job) is None


def test_users_do_not_see_each_others_kits(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    mine = portal.call(_job, uow, ALICE, "A")
    portal.call(_add, uow, ALICE, mine)

    assert portal.call(_latest, uow, BOB, mine) is None


def test_a_rolled_back_save_leaves_nothing_and_spends_no_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE, "A")

    async def rolled_back() -> None:
        async with uow() as tx:
            await tx.interview_kits.add(ALICE, KitId(_id()), job, _kit("lost"), NOW)

    portal.call(rolled_back)

    assert portal.call(_latest, uow, ALICE, job) is None
    kept = portal.call(_add, uow, ALICE, job, _kit("kept"))
    assert (kept.number, kept.version) == (1, 1)


def test_parallel_saves_for_one_job_get_distinct_consecutive_versions(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE, "A")

    async def race() -> list[KitVersion]:
        return list(
            await asyncio.gather(
                *(_add(uow, ALICE, job, _kit(str(n))) for n in range(6))
            )
        )

    saved = portal.call(race)

    assert sorted(item.version for item in saved) == [1, 2, 3, 4, 5, 6]
    assert sorted(item.number for item in saved) == [1, 2, 3, 4, 5, 6]


def test_the_content_is_stored_in_the_v1_json_shape(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE, "A")
    portal.call(_add, uow, ALICE, job, _kit("a", topic=4))

    async def content() -> dict[str, Any]:
        async with engine.connect() as conn:
            row = await conn.scalar(text("SELECT content FROM interview_kits"))
            assert isinstance(row, dict)
            return row

    stored = portal.call(content)

    assert stored["questions"][0] == {
        "kind": "technical",
        "question": "Question a1?",
        "topic_id": 4,
    }
    assert stored["questions"][1]["topic_id"] is None
    assert stored["stories"][0] == {
        "title": "Story a1",
        "situation": "Situation 1",
        "task": "Task 1",
        "action": "Action 1",
        "result": "Result 1",
        "fact_ids": [1, 11],
    }
    assert stored["company_questions"] == ["Ask a1?", "Ask a2?", "Ask a3?"]
    assert set(stored) == {"questions", "stories", "company_questions"}


def test_deleting_a_job_deletes_its_kits(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE, "A")
    portal.call(_add, uow, ALICE, job)

    portal.call(_run, engine, "DELETE FROM jobs")

    async def count() -> int:
        async with engine.connect() as conn:
            return int(
                await conn.scalar(text("SELECT count(*) FROM interview_kits")) or 0
            )

    assert portal.call(count) == 0


@pytest.mark.parametrize(
    "values",
    [
        "UPDATE interview_kits SET version = 0",
        "UPDATE interview_kits SET kit_number = 0",
        "UPDATE interview_kit_counters SET last_number = -1",
    ],
)
def test_the_database_refuses_a_value_outside_the_rules(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine, values: str
) -> None:
    job = portal.call(_job, uow, ALICE, "A")
    portal.call(_add, uow, ALICE, job)

    with pytest.raises(IntegrityError):
        portal.call(_run, engine, values)


def test_the_number_is_unique_per_user_and_the_version_per_job(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE, "A")
    portal.call(_add, uow, ALICE, job)
    portal.call(_add, uow, ALICE, job)

    with pytest.raises(IntegrityError):
        portal.call(_run, engine, "UPDATE interview_kits SET kit_number = 1")
    with pytest.raises(IntegrityError):
        portal.call(_run, engine, "UPDATE interview_kits SET version = 1")


def test_the_tables_exist_with_the_planned_columns(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    async def columns(table: str) -> dict[str, str]:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = :table"
                ),
                {"table": table},
            )
            return {row[0]: row[1] for row in rows}

    assert portal.call(columns, "interview_kits") == {
        "id": "uuid",
        "user_id": "uuid",
        "kit_number": "integer",
        "job_id": "uuid",
        "version": "integer",
        "content": "jsonb",
        "created_at": "timestamp with time zone",
    }
    assert portal.call(columns, "interview_kit_counters") == {
        "user_id": "uuid",
        "last_number": "integer",
    }
