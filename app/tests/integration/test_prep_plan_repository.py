"""План теми в Postgres: кроки з номерами на користувача, заміна невиконаних, виконання, «готово», схема для ETL."""

from datetime import datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.identity.ids import UserId
from domain.prep.ids import StepId
from domain.prep.plan import NewStep, Resource, StepKind
from domain.prep.topic import PrepTopic
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW
from tests.integration.test_prep_repository import (
    _all,
    _id,
    _job,
    _run,
    _save,
    _topic,
    only,
    uow,
)

__all__ = ["uow"]

LATER = NOW + timedelta(days=2)


def _step(
    kind: StepKind = StepKind.LEARN,
    title: str = "Крок",
    minutes: int = 30,
    details: str = "",
    resources: tuple[Resource, ...] = (),
) -> NewStep:
    return NewStep(kind, title, minutes, details, resources)


async def _topic_for(uow: UnitOfWorkFactory, user: UserId, slug: str = "go") -> int:
    job = await _job(uow, user, f"Job {slug}")
    return await _save(uow, user, job, _topic(slug))


async def _replace(
    uow: UnitOfWorkFactory, user: UserId, topic: int, *steps: NewStep
) -> None:
    async with uow() as tx:
        await tx.prep_topics.replace_pending_steps(
            user, topic, [(StepId(_id()), step) for step in steps]
        )
        await tx.commit()


async def _get(uow: UnitOfWorkFactory, user: UserId, topic: int) -> PrepTopic | None:
    async with uow() as tx:
        return await tx.prep_topics.get(user, topic)


async def _complete(
    uow: UnitOfWorkFactory, user: UserId, step: int, note: str = "", at: datetime = NOW
) -> int | None:
    async with uow() as tx:
        found = await tx.prep_topics.complete_step(user, step, note, at)
        await tx.commit()
        return found


async def _ready(
    uow: UnitOfWorkFactory, user: UserId, topic: int, ready: bool, at: datetime = NOW
) -> None:
    async with uow() as tx:
        await tx.prep_topics.set_ready(user, topic, ready=ready, now=at)
        await tx.commit()


def _must(topic: PrepTopic | None) -> PrepTopic:
    assert topic is not None, "теми нема"
    return topic


def _steps(topic: PrepTopic | None) -> list[tuple[int, int, str]]:
    return [(s.number, s.position, s.title) for s in _must(topic).steps]


def test_a_topic_without_a_plan_has_no_steps_and_is_not_ready(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(_topic_for, uow, ALICE)

    topic = _must(portal.call(_get, uow, ALICE, number))

    assert (topic.steps, topic.ready_at) == ((), None)


def test_get_returns_the_whole_topic_with_its_jobs_and_none_for_a_missing_or_foreign_one(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(_topic_for, uow, ALICE)

    topic = _must(portal.call(_get, uow, ALICE, number))

    assert topic == only(portal.call(_all, uow, ALICE))
    assert [job.gap for job in topic.jobs] == ["Прогалина"]
    assert portal.call(_get, uow, ALICE, 9) is None
    assert portal.call(_get, uow, BOB, number) is None


def test_a_plan_is_stored_in_order_with_every_field_and_numbers_from_one(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(_topic_for, uow, ALICE)
    rich = _step(
        StepKind.PRACTICE,
        "Запити",
        90,
        "Що зробити.\nДруга лінія.",
        (
            Resource("Док", "https://example.com/a"),
            Resource("Книга", "http://b.example"),
        ),
    )

    portal.call(
        _replace,
        uow,
        ALICE,
        number,
        _step(title="Теорія"),
        rich,
        _step(StepKind.CHECK, "Перевірка"),
    )

    steps = _must(portal.call(_get, uow, ALICE, number)).steps
    assert [(s.number, s.position, s.kind, s.title, s.minutes) for s in steps] == [
        (1, 1, StepKind.LEARN, "Теорія", 30),
        (2, 2, StepKind.PRACTICE, "Запити", 90),
        (3, 3, StepKind.CHECK, "Перевірка", 30),
    ]
    assert (steps[1].details, steps[1].resources) == (rich.details, rich.resources)
    assert all(s.done_at is None and s.note == "" for s in steps)
    assert len({s.id for s in steps}) == 3


def test_a_replacement_drops_the_pending_steps_keeps_the_done_ones_and_appends_after_them(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(_topic_for, uow, ALICE)
    portal.call(
        _replace,
        uow,
        ALICE,
        number,
        _step(title="A"),
        _step(title="B"),
        _step(title="C"),
    )
    portal.call(_complete, uow, ALICE, 2, "ok")

    portal.call(_replace, uow, ALICE, number, _step(title="D"), _step(title="E"))

    topic = _must(portal.call(_get, uow, ALICE, number))
    assert _steps(topic) == [(2, 2, "B"), (4, 3, "D"), (5, 4, "E")]
    assert (topic.steps[0].done_at, topic.steps[0].note) == (NOW, "ok")


def test_numbers_of_dropped_steps_are_not_reused(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(_topic_for, uow, ALICE)
    portal.call(_replace, uow, ALICE, number, _step(), _step())

    portal.call(_replace, uow, ALICE, number, _step(title="Нова"))

    assert _steps(portal.call(_get, uow, ALICE, number)) == [(3, 1, "Нова")]


def test_step_numbers_run_across_the_topics_of_a_user_and_restart_for_another_user(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_topic_for, uow, ALICE, "go")
    second = portal.call(_topic_for, uow, ALICE, "rust")
    bobs = portal.call(_topic_for, uow, BOB, "sql")
    portal.call(_replace, uow, ALICE, first, _step(title="a"), _step(title="b"))
    portal.call(_replace, uow, ALICE, second, _step(title="c"))
    portal.call(_replace, uow, BOB, bobs, _step(title="d"))

    assert _steps(portal.call(_get, uow, ALICE, first)) == [(1, 1, "a"), (2, 2, "b")]
    assert _steps(portal.call(_get, uow, ALICE, second)) == [(3, 1, "c")]
    assert _steps(portal.call(_get, uow, BOB, bobs)) == [(1, 1, "d")]


def test_replacing_the_plan_of_one_topic_leaves_another_topic_alone(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_topic_for, uow, ALICE, "go")
    second = portal.call(_topic_for, uow, ALICE, "rust")
    portal.call(_replace, uow, ALICE, first, _step(title="a"))
    portal.call(_replace, uow, ALICE, second, _step(title="b"))

    portal.call(_replace, uow, ALICE, first, _step(title="c"))

    assert _steps(portal.call(_get, uow, ALICE, second)) == [(2, 1, "b")]


def test_a_rolled_back_replacement_changes_nothing_and_spends_no_numbers(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(_topic_for, uow, ALICE)
    portal.call(_replace, uow, ALICE, number, _step(title="Стара"))

    async def rolled_back() -> None:
        async with uow() as tx:
            await tx.prep_topics.replace_pending_steps(
                ALICE, number, [(StepId(_id()), _step(title="Втрачена"))]
            )

    portal.call(rolled_back)

    assert _steps(portal.call(_get, uow, ALICE, number)) == [(1, 1, "Стара")]
    portal.call(_replace, uow, ALICE, number, _step(title="Нова"))
    assert _steps(portal.call(_get, uow, ALICE, number)) == [(2, 1, "Нова")]


def test_completing_a_step_sets_the_date_and_the_note_and_returns_the_topic_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_topic_for, uow, ALICE, "go")
    second = portal.call(_topic_for, uow, ALICE, "rust")
    portal.call(_replace, uow, ALICE, second, _step(), _step())

    found = portal.call(_complete, uow, ALICE, 2, "Зробив", LATER)

    assert found == second
    steps = _must(portal.call(_get, uow, ALICE, second)).steps
    assert [(s.done_at, s.note) for s in steps] == [(None, ""), (LATER, "Зробив")]


def test_completing_again_keeps_the_first_date_and_replaces_a_non_empty_note(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(_topic_for, uow, ALICE)
    portal.call(_replace, uow, ALICE, number, _step())
    portal.call(_complete, uow, ALICE, 1, "Перша", NOW)

    portal.call(_complete, uow, ALICE, 1, "Друга", LATER)
    after_second = _must(portal.call(_get, uow, ALICE, number)).steps[0]
    portal.call(_complete, uow, ALICE, 1, "", LATER + timedelta(days=1))
    after_empty = _must(portal.call(_get, uow, ALICE, number)).steps[0]

    assert (after_second.done_at, after_second.note) == (NOW, "Друга")
    assert (after_empty.done_at, after_empty.note) == (NOW, "Друга")


def test_a_missing_or_foreign_step_is_none_and_changes_nothing(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(_topic_for, uow, ALICE)
    portal.call(_replace, uow, ALICE, number, _step())

    assert portal.call(_complete, uow, ALICE, 99, "x") is None
    assert portal.call(_complete, uow, BOB, 1, "x") is None
    step = _must(portal.call(_get, uow, ALICE, number)).steps[0]
    assert (step.done_at, step.note) == (None, "")


def test_set_ready_marks_the_topic_keeps_the_first_date_and_takes_it_back(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(_topic_for, uow, ALICE)
    portal.call(_replace, uow, ALICE, number, _step())

    portal.call(_ready, uow, ALICE, number, True, NOW)
    portal.call(_ready, uow, ALICE, number, True, LATER)
    again = _must(portal.call(_get, uow, ALICE, number))
    portal.call(_ready, uow, ALICE, number, False)
    taken_back = _must(portal.call(_get, uow, ALICE, number))

    assert again.ready_at == NOW
    assert taken_back.ready_at is None
    assert len(taken_back.steps) == 1


def test_set_ready_touches_only_that_users_topic(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    mine = portal.call(_topic_for, uow, ALICE, "go")
    portal.call(_topic_for, uow, BOB, "go")

    portal.call(_ready, uow, ALICE, mine, True)

    assert _must(portal.call(_get, uow, ALICE, mine)).ready_at == NOW
    assert _must(portal.call(_get, uow, BOB, mine)).ready_at is None


def test_all_returns_the_steps_of_every_topic_in_plan_order(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_topic_for, uow, ALICE, "go")
    second = portal.call(_topic_for, uow, ALICE, "rust")
    portal.call(_replace, uow, ALICE, first, _step(title="a"), _step(title="b"))
    portal.call(_replace, uow, ALICE, second, _step(title="c"))

    topics = portal.call(_all, uow, ALICE)

    assert [_steps(topic) for topic in topics] == [
        [(1, 1, "a"), (2, 2, "b")],
        [(3, 1, "c")],
    ]


def test_saving_a_topic_again_keeps_its_plan_and_its_ready_mark(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE, "A")
    number = portal.call(_save, uow, ALICE, job, _topic("go"))
    portal.call(_replace, uow, ALICE, number, _step())
    portal.call(_ready, uow, ALICE, number, True)

    portal.call(_save, uow, ALICE, job, _topic("go", title="Нова назва"))

    topic = _must(portal.call(_get, uow, ALICE, number))
    assert (topic.title, len(topic.steps), topic.ready_at) == ("Нова назва", 1, NOW)


def test_deleting_a_topic_deletes_its_steps(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    number = portal.call(_topic_for, uow, ALICE)
    portal.call(_replace, uow, ALICE, number, _step(), _step())

    portal.call(_run, engine, "DELETE FROM prep_topics")

    async def count() -> int:
        async with engine.connect() as conn:
            return int(await conn.scalar(text("SELECT count(*) FROM prep_steps")) or 0)

    assert portal.call(count) == 0


@pytest.mark.parametrize(
    "values",
    [
        "UPDATE prep_steps SET kind = 'read'",
        "UPDATE prep_steps SET minutes = 0",
        "UPDATE prep_steps SET step_number = 0",
        "UPDATE prep_steps SET position = 0",
    ],
)
def test_the_database_refuses_a_step_outside_the_rules(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine, values: str
) -> None:
    number = portal.call(_topic_for, uow, ALICE)
    portal.call(_replace, uow, ALICE, number, _step())
    assert len(_must(portal.call(_get, uow, ALICE, number)).steps) == 1

    with pytest.raises(IntegrityError):
        portal.call(_run, engine, values)


def test_the_step_number_is_unique_per_user_and_the_position_per_topic(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    number = portal.call(_topic_for, uow, ALICE)
    portal.call(_replace, uow, ALICE, number, _step(), _step())
    assert len(_must(portal.call(_get, uow, ALICE, number)).steps) == 2

    with pytest.raises(IntegrityError):
        portal.call(_run, engine, "UPDATE prep_steps SET step_number = 1")
    with pytest.raises(IntegrityError):
        portal.call(_run, engine, "UPDATE prep_steps SET position = 1")


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

    assert portal.call(columns, "prep_steps") == {
        "id": "uuid",
        "user_id": "uuid",
        "topic_id": "uuid",
        "step_number": "integer",
        "position": "integer",
        "kind": "text",
        "title": "text",
        "details": "text",
        "resources": "jsonb",
        "minutes": "integer",
        "done_at": "timestamp with time zone",
        "note": "text",
    }
    assert portal.call(columns, "prep_step_counters") == {
        "user_id": "uuid",
        "last_number": "integer",
    }
    assert portal.call(columns, "prep_topics")["ready_at"] == "timestamp with time zone"


def test_a_replacement_without_new_steps_drops_the_pending_ones_and_spends_no_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(_topic_for, uow, ALICE)
    portal.call(_replace, uow, ALICE, number, _step(title="A"), _step(title="B"))
    portal.call(_complete, uow, ALICE, 1)

    portal.call(_replace, uow, ALICE, number)
    portal.call(_replace, uow, ALICE, number, _step(title="C"))

    assert _steps(portal.call(_get, uow, ALICE, number)) == [(1, 1, "A"), (3, 2, "C")]
