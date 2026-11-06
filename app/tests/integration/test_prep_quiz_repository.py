"""PostgresPrepQuestions на справжній базі: номери на користувача, дубль у темі, розклад Leitner,
історія відповідей, схема для ETL."""

from datetime import date, timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.identity.ids import UserId
from domain.prep.ids import AnswerId, QuestionId
from domain.prep.quiz import Answer, NewQuestion, PastAnswer, PrepQuestion, Schedule
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW
from tests.integration.test_prep_plan_repository import _topic_for
from tests.integration.test_prep_repository import _id, _run, uow

__all__ = ["uow"]

TODAY = date(2026, 1, 1)
LATER = NOW + timedelta(days=2)
NEW = Schedule(1, TODAY)
MOVED = Schedule(2, date(2026, 1, 3))


def _question(text: str = "What is an index?", *points: str) -> NewQuestion:
    return NewQuestion(text, points or ("Speeds up reads", "Costs writes"))


async def _add(
    uow: UnitOfWorkFactory,
    user: UserId,
    topic: int,
    question: NewQuestion | None = None,
    schedule: Schedule = NEW,
) -> int | None:
    async with uow() as tx:
        number = await tx.prep_questions.add(
            user,
            QuestionId(_id()),
            topic,
            question or _question(),
            schedule,
            NOW,
        )
        await tx.commit()
        return number


async def _all(
    uow: UnitOfWorkFactory, user: UserId, topic: int | None = None
) -> list[PrepQuestion]:
    async with uow() as tx:
        return await tx.prep_questions.all(user, topic)


async def _get(
    uow: UnitOfWorkFactory, user: UserId, number: int
) -> PrepQuestion | None:
    async with uow() as tx:
        return await tx.prep_questions.get(user, number)


async def _record(
    uow: UnitOfWorkFactory,
    user: UserId,
    number: int,
    grade: int = 4,
    answer: str = "It speeds up reads.",
    feedback: str = "Добре.",
    schedule: Schedule = MOVED,
    at: Any = NOW,
) -> None:
    async with uow() as tx:
        await tx.prep_questions.record(
            user,
            AnswerId(_id()),
            number,
            Answer(grade, answer, feedback),
            schedule,
            at,
        )
        await tx.commit()


async def _answers(
    uow: UnitOfWorkFactory, user: UserId, number: int
) -> list[PastAnswer]:
    async with uow() as tx:
        return await tx.prep_questions.answers(user, number)


def _must(question: PrepQuestion | None) -> PrepQuestion:
    assert question is not None, "питання нема"
    return question


def test_a_new_question_reads_back_whole_with_the_title_of_its_topic(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    topic = portal.call(_topic_for, uow, ALICE, "mysql")
    question_id = QuestionId(_id())

    async def add() -> int | None:
        async with uow() as tx:
            number = await tx.prep_questions.add(
                ALICE, question_id, topic, _question(), Schedule(1, TODAY), NOW
            )
            await tx.commit()
            return number

    number = portal.call(add)

    assert number == 1
    assert _must(portal.call(_get, uow, ALICE, 1)) == PrepQuestion(
        id=question_id,
        number=1,
        topic_number=topic,
        topic_title="Тема mysql",
        question="What is an index?",
        answer_points=("Speeds up reads", "Costs writes"),
        box=1,
        due_on=TODAY,
        created_at=NOW,
    )


def test_numbers_run_across_the_topics_of_a_user_and_restart_for_another_user(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_topic_for, uow, ALICE, "go")
    second = portal.call(_topic_for, uow, ALICE, "rust")
    bobs = portal.call(_topic_for, uow, BOB, "sql")

    numbers = [
        portal.call(_add, uow, ALICE, first, _question("A?")),
        portal.call(_add, uow, ALICE, second, _question("B?")),
        portal.call(_add, uow, BOB, bobs, _question("A?")),
        portal.call(_add, uow, ALICE, first, _question("C?")),
    ]

    assert numbers == [1, 2, 1, 3]


def test_the_same_question_in_a_topic_is_a_duplicate_whatever_the_case_and_spaces(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)
    portal.call(_add, uow, ALICE, topic, _question("What is an index?"))

    again = portal.call(_add, uow, ALICE, topic, _question("  what IS   an INDEX?"))

    assert again is None
    assert [q.question for q in portal.call(_all, uow, ALICE)] == ["What is an index?"]


def test_a_duplicate_spends_no_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)
    portal.call(_add, uow, ALICE, topic, _question("A?"))
    portal.call(_add, uow, ALICE, topic, _question("a?"))

    assert portal.call(_add, uow, ALICE, topic, _question("B?")) == 2


def test_the_same_question_in_another_topic_or_for_another_user_is_not_a_duplicate(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_topic_for, uow, ALICE, "go")
    second = portal.call(_topic_for, uow, ALICE, "rust")
    bobs = portal.call(_topic_for, uow, BOB, "sql")
    portal.call(_add, uow, ALICE, first)

    assert portal.call(_add, uow, ALICE, second) == 2
    assert portal.call(_add, uow, BOB, bobs) == 1


def test_a_rolled_back_question_spends_no_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)

    async def add_without_commit() -> None:
        async with uow() as tx:
            await tx.prep_questions.add(
                ALICE,
                QuestionId(_id()),
                topic,
                _question("A?"),
                Schedule(1, TODAY),
                NOW,
            )

    portal.call(add_without_commit)

    assert portal.call(_all, uow, ALICE) == []
    assert portal.call(_add, uow, ALICE, topic, _question("B?")) == 1


def test_all_lists_a_user_questions_by_number_and_can_filter_by_topic(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_topic_for, uow, ALICE, "go")
    second = portal.call(_topic_for, uow, ALICE, "rust")
    bobs = portal.call(_topic_for, uow, BOB, "sql")
    portal.call(_add, uow, ALICE, first, _question("A?"))
    portal.call(_add, uow, ALICE, second, _question("B?"))
    portal.call(_add, uow, BOB, bobs, _question("X?"))
    portal.call(_add, uow, ALICE, first, _question("C?"))

    everything = portal.call(_all, uow, ALICE)
    only_first = portal.call(_all, uow, ALICE, first)

    assert [(q.number, q.topic_number, q.question) for q in everything] == [
        (1, first, "A?"),
        (2, second, "B?"),
        (3, first, "C?"),
    ]
    assert [q.number for q in only_first] == [1, 3]
    assert [q.topic_title for q in everything] == ["Тема go", "Тема rust", "Тема go"]
    assert [q.question for q in portal.call(_all, uow, BOB)] == ["X?"]


def test_get_returns_own_questions_and_none_for_a_missing_or_foreign_one(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)
    portal.call(_add, uow, ALICE, topic)

    assert _must(portal.call(_get, uow, ALICE, 1)).question == "What is an index?"
    assert portal.call(_get, uow, ALICE, 9) is None
    assert portal.call(_get, uow, BOB, 1) is None


def test_the_order_of_key_points_is_kept(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)
    portal.call(_add, uow, ALICE, topic, _question("Q?", "zeta", "alpha", "mid"))

    assert _must(portal.call(_get, uow, ALICE, 1)).answer_points == (
        "zeta",
        "alpha",
        "mid",
    )


def test_recording_an_answer_moves_the_question_and_adds_a_history_row(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)
    portal.call(_add, uow, ALICE, topic)

    portal.call(_record, uow, ALICE, 1)

    moved = _must(portal.call(_get, uow, ALICE, 1))
    assert (moved.box, moved.due_on) == (2, date(2026, 1, 3))
    assert portal.call(_answers, uow, ALICE, 1) == [
        PastAnswer(4, "It speeds up reads.", "Добре.", 2, NOW)
    ]


def test_every_attempt_stays_in_the_history_oldest_first(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)
    portal.call(_add, uow, ALICE, topic)

    portal.call(_record, uow, ALICE, 1, 4, "First", "F1", Schedule(2, date(2026, 1, 3)))
    portal.call(
        _record, uow, ALICE, 1, 1, "Second", "F2", Schedule(1, date(2026, 1, 4)), LATER
    )

    assert portal.call(_answers, uow, ALICE, 1) == [
        PastAnswer(4, "First", "F1", 2, NOW),
        PastAnswer(1, "Second", "F2", 1, LATER),
    ]
    assert _must(portal.call(_get, uow, ALICE, 1)).box == 1


def test_an_empty_answer_and_feedback_are_stored(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)
    portal.call(_add, uow, ALICE, topic)

    portal.call(_record, uow, ALICE, 1, 0, "", "", Schedule(1, date(2026, 1, 2)))

    assert portal.call(_answers, uow, ALICE, 1) == [PastAnswer(0, "", "", 1, NOW)]


def test_a_rolled_back_answer_changes_nothing(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)
    portal.call(_add, uow, ALICE, topic)

    async def record_without_commit() -> None:
        async with uow() as tx:
            await tx.prep_questions.record(
                ALICE,
                AnswerId(_id()),
                1,
                Answer(5, "a", "f"),
                Schedule(2, date(2026, 1, 3)),
                NOW,
            )

    portal.call(record_without_commit)

    assert _must(portal.call(_get, uow, ALICE, 1)).box == 1
    assert portal.call(_answers, uow, ALICE, 1) == []


def test_the_history_of_a_missing_or_foreign_question_is_empty(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)
    portal.call(_add, uow, ALICE, topic)
    portal.call(_record, uow, ALICE, 1)

    assert portal.call(_answers, uow, ALICE, 9) == []
    assert portal.call(_answers, uow, BOB, 1) == []


def test_deleting_a_topic_deletes_its_questions_and_their_history(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)
    portal.call(_add, uow, ALICE, topic)
    portal.call(_record, uow, ALICE, 1)

    portal.call(_run, engine, "DELETE FROM prep_topics")

    async def counts() -> tuple[int, int]:
        async with engine.connect() as conn:
            questions = await conn.scalar(text("SELECT count(*) FROM prep_questions"))
            answers = await conn.scalar(text("SELECT count(*) FROM prep_answers"))
            return int(questions or 0), int(answers or 0)

    assert portal.call(counts) == (0, 0)


@pytest.mark.parametrize(
    "values",
    [
        "UPDATE prep_questions SET box = 0",
        "UPDATE prep_questions SET box = 6",
        "UPDATE prep_questions SET question_number = 0",
        "UPDATE prep_answers SET grade = 6",
        "UPDATE prep_answers SET grade = -1",
        "UPDATE prep_answers SET box = 0",
    ],
)
def test_the_database_refuses_a_value_outside_the_rules(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine, values: str
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)
    portal.call(_add, uow, ALICE, topic)
    portal.call(_record, uow, ALICE, 1)
    assert len(portal.call(_all, uow, ALICE)) == 1

    with pytest.raises(IntegrityError):
        portal.call(_run, engine, values)


def test_the_question_number_is_unique_per_user_and_the_text_per_topic(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    topic = portal.call(_topic_for, uow, ALICE)
    portal.call(_add, uow, ALICE, topic, _question("A?"))
    portal.call(_add, uow, ALICE, topic, _question("B?"))
    assert len(portal.call(_all, uow, ALICE)) == 2

    with pytest.raises(IntegrityError):
        portal.call(_run, engine, "UPDATE prep_questions SET question_number = 1")
    with pytest.raises(IntegrityError):
        portal.call(_run, engine, "UPDATE prep_questions SET question_hash = 'same'")


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

    assert portal.call(columns, "prep_questions") == {
        "id": "uuid",
        "user_id": "uuid",
        "topic_id": "uuid",
        "question_number": "integer",
        "question": "text",
        "question_hash": "text",
        "answer_points": "ARRAY",
        "box": "integer",
        "due_on": "date",
        "created_at": "timestamp with time zone",
    }
    assert portal.call(columns, "prep_answers") == {
        "id": "uuid",
        "question_id": "uuid",
        "grade": "integer",
        "answer": "text",
        "feedback": "text",
        "box": "integer",
        "answered_at": "timestamp with time zone",
    }
    assert portal.call(columns, "prep_question_counters") == {
        "user_id": "uuid",
        "last_number": "integer",
    }
