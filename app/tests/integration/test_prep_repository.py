"""PostgresPrepTopics на справжній базі: slug і номери на користувача, прив'язки, скор з аналізу, схема для ETL."""

import asyncio
from datetime import date
from uuid import UUID

from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.analysis.analysis import JobAnalysis
from domain.analysis.ids import AnalysisId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.prep.ids import TopicId
from domain.prep.topic import NewTopic, PrepTopic, TopicJob, TopicKind
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, posting, uow

__all__ = ["uow"]

_ids = iter(range(1, 10_000))


def _id() -> UUID:
    return UUID(int=0xD000 + next(_ids))


def _topic(slug: str = "go", **fields: object) -> NewTopic:
    base = {"title": f"Тема {slug}", "kind": TopicKind.TECH, "summary": "Опис."}
    return NewTopic(slug=slug, **(base | fields))  # type: ignore[arg-type]


async def _job(
    uow: UnitOfWorkFactory,
    user: UserId,
    title: str,
    score: int | None = 70,
) -> JobId:
    job_id = JobId(_id())
    async with uow() as tx:
        await tx.jobs.add(
            user,
            job_id,
            posting(f"Опис {title}", title=title, company="Acme"),
            NOW,
        )
        if score is not None:
            await tx.analyses.save(
                user, AnalysisId(_id()), job_id, JobAnalysis(score, "S."), (), NOW
            )
        await tx.commit()
    return job_id


async def _save(
    uow: UnitOfWorkFactory,
    user: UserId,
    job: JobId,
    topic: NewTopic,
    gap: str = "Прогалина",
    topic_id: TopicId | None = None,
) -> int:
    async with uow() as tx:
        number = await tx.prep_topics.save(
            user, topic_id or TopicId(_id()), job, topic, gap, NOW
        )
        await tx.commit()
    return number


async def _all(uow: UnitOfWorkFactory, user: UserId) -> list[PrepTopic]:
    async with uow() as tx:
        return await tx.prep_topics.all(user)


def only(items: list[PrepTopic]) -> PrepTopic:
    assert len(items) == 1, items
    return items[0]


async def _run(engine: AsyncEngine, sql: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql))


def test_a_new_topic_reads_back_whole_with_its_job_and_the_current_score(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE, "Backend", 82)
    topic_id = TopicId(_id())
    topic = _topic("mysql", deadline=date(2026, 3, 15), kind=TopicKind.DOMAIN)

    number = portal.call(_save, uow, ALICE, job, topic, "Немає MySQL", topic_id)

    saved = only(portal.call(_all, uow, ALICE))
    assert number == 1
    assert saved == PrepTopic(
        id=topic_id,
        number=1,
        slug="mysql",
        title="Тема mysql",
        kind=TopicKind.DOMAIN,
        summary="Опис.",
        deadline=date(2026, 3, 15),
        created_at=NOW,
        jobs=(TopicJob(1, "Backend", "Acme", 82, "Немає MySQL"),),
    )
    assert saved.priority == 82


def test_the_number_is_per_user_and_starts_from_one(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    alice_job = portal.call(_job, uow, ALICE, "A")
    bob_job = portal.call(_job, uow, BOB, "B")
    portal.call(_save, uow, ALICE, alice_job, _topic("go"))
    portal.call(_save, uow, ALICE, alice_job, _topic("rust"))
    portal.call(_save, uow, BOB, bob_job, _topic("sql"))

    alice = portal.call(_all, uow, ALICE)
    bob = portal.call(_all, uow, BOB)
    assert [(topic.slug, topic.number) for topic in alice] == [("go", 1), ("rust", 2)]
    assert [(topic.slug, topic.number) for topic in bob] == [("sql", 1)]


def test_an_existing_slug_replaces_the_fields_and_keeps_the_number_and_the_key(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE, "A")
    first_id = TopicId(_id())
    portal.call(
        _save, uow, ALICE, job, _topic("go", deadline=date(2026, 3, 1)), "g", first_id
    )

    number = portal.call(
        _save,
        uow,
        ALICE,
        job,
        _topic(
            "go", title="Нова", kind=TopicKind.BEHAVIORAL, summary="", deadline=None
        ),
    )

    saved = only(portal.call(_all, uow, ALICE))
    assert number == 1
    assert (saved.id, saved.number) == (first_id, 1)
    assert (saved.title, saved.kind, saved.summary, saved.deadline) == (
        "Нова",
        TopicKind.BEHAVIORAL,
        "",
        None,
    )
    assert saved.created_at == NOW


def test_a_repeat_for_the_same_job_replaces_the_gap_without_a_second_link(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE, "A")
    portal.call(_save, uow, ALICE, job, _topic("go"), "Стара")
    portal.call(_save, uow, ALICE, job, _topic("go"), "Нова")

    saved = only(portal.call(_all, uow, ALICE))
    assert [item.gap for item in saved.jobs] == ["Нова"]


def test_one_topic_links_several_jobs_ordered_by_job_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_job, uow, ALICE, "Перша", 80)
    second = portal.call(_job, uow, ALICE, "Друга", 55)
    portal.call(_save, uow, ALICE, second, _topic("go"), "Друга прогалина")
    portal.call(_save, uow, ALICE, first, _topic("go"), "Перша прогалина")

    saved = only(portal.call(_all, uow, ALICE))
    assert [(item.job_number, item.score, item.gap) for item in saved.jobs] == [
        (1, 80, "Перша прогалина"),
        (2, 55, "Друга прогалина"),
    ]
    assert saved.priority == 135


def test_a_hidden_job_still_counts_and_a_new_analysis_changes_the_score(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE, "A", 30)
    portal.call(_save, uow, ALICE, job, _topic("go"))
    portal.call(
        _run,
        engine,
        "UPDATE jobs SET dismissed_at = now(), dismiss_reason = 'не цікаво'",
    )
    portal.call(_run, engine, "UPDATE job_analyses SET score = 75")

    saved = only(portal.call(_all, uow, ALICE))
    assert saved.priority == 75


def test_users_do_not_see_each_others_topics(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_save, uow, ALICE, portal.call(_job, uow, ALICE, "A"), _topic("go"))

    assert portal.call(_all, uow, BOB) == []


def test_changing_a_slug_of_one_user_leaves_the_other_users_topic_alone(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    alice_job = portal.call(_job, uow, ALICE, "A")
    bob_job = portal.call(_job, uow, BOB, "B", 10)
    portal.call(_save, uow, ALICE, alice_job, _topic("go", title="Олена"))
    portal.call(_save, uow, BOB, bob_job, _topic("go", title="Богдан"))

    portal.call(_save, uow, BOB, bob_job, _topic("go", title="Богдан 2"))

    assert [topic.title for topic in portal.call(_all, uow, ALICE)] == ["Олена"]
    assert [topic.title for topic in portal.call(_all, uow, BOB)] == ["Богдан 2"]


def test_a_rolled_back_save_leaves_nothing_and_spends_no_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE, "A")

    async def rolled_back() -> None:
        async with uow() as tx:
            await tx.prep_topics.save(
                ALICE, TopicId(_id()), job, _topic("lost"), "g", NOW
            )

    portal.call(rolled_back)

    assert portal.call(_all, uow, ALICE) == []
    assert portal.call(_save, uow, ALICE, job, _topic("kept")) == 1


def test_deleting_a_job_drops_its_link_but_keeps_the_topic(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    first = portal.call(_job, uow, ALICE, "Перша")
    second = portal.call(_job, uow, ALICE, "Друга")
    portal.call(_save, uow, ALICE, first, _topic("go"))
    portal.call(_save, uow, ALICE, second, _topic("go"))

    portal.call(_run, engine, "DELETE FROM jobs WHERE title = 'Перша'")

    saved = only(portal.call(_all, uow, ALICE))
    assert [item.job_number for item in saved.jobs] == [2]


def test_parallel_saves_of_one_new_slug_create_one_topic(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    jobs = [portal.call(_job, uow, ALICE, f"Job {n}") for n in range(6)]

    async def race() -> list[int]:
        return list(
            await asyncio.gather(
                *(
                    _save(uow, ALICE, job, _topic("go"), f"gap {n}")
                    for n, job in enumerate(jobs)
                )
            )
        )

    numbers = portal.call(race)

    assert set(numbers) == {1}
    saved = only(portal.call(_all, uow, ALICE))
    assert len(saved.jobs) == 6


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

    assert portal.call(columns, "prep_topics") == {
        "id": "uuid",
        "user_id": "uuid",
        "topic_number": "integer",
        "slug": "text",
        "title": "text",
        "kind": "text",
        "summary": "text",
        "deadline": "date",
        "created_at": "timestamp with time zone",
        "ready_at": "timestamp with time zone",
    }
    assert portal.call(columns, "prep_topic_jobs") == {
        "topic_id": "uuid",
        "job_id": "uuid",
        "gap": "text",
    }
    assert portal.call(columns, "prep_topic_counters") == {
        "user_id": "uuid",
        "last_number": "integer",
    }
