"""Статус теми з кроків, відсоток готовності теми, готовність вакансії, хвилини, що лишились.

Поведінка — як у v1 (`origin/main` `99a2007`, `core/domain/prep.py`); «готово» ставить лише користувач.
"""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from domain.prep.ids import StepId, TopicId
from domain.prep.plan import PrepStep, StepKind
from domain.prep.topic import PrepTopic, TopicKind, TopicStatus, readiness

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
LEARN, PRACTICE, CHECK = StepKind.LEARN, StepKind.PRACTICE, StepKind.CHECK


def step(
    number: int, kind: StepKind, *, done: bool = False, minutes: int = 30
) -> PrepStep:
    return PrepStep(
        id=StepId(UUID(int=number)),
        number=number,
        position=number,
        kind=kind,
        title=f"Крок {number}",
        minutes=minutes,
        details="",
        resources=(),
        done_at=NOW if done else None,
    )


def topic(*steps: PrepStep, ready: bool = False) -> PrepTopic:
    return PrepTopic(
        id=TopicId(UUID(int=1)),
        number=1,
        slug="mysql",
        title="MySQL",
        kind=TopicKind.TECH,
        summary="",
        deadline=None,
        created_at=NOW,
        steps=steps,
        ready_at=NOW if ready else None,
    )


def with_done(total: int, done: int) -> PrepTopic:
    """Тема з `total` кроків learn, перші `done` виконані."""
    return topic(*(step(n, LEARN, done=n <= done) for n in range(1, total + 1)))


def test_a_topic_marked_ready_is_ready_whatever_its_steps() -> None:
    assert topic(ready=True).status is TopicStatus.READY
    assert topic(step(1, LEARN), ready=True).status is TopicStatus.READY
    assert topic(step(1, PRACTICE, done=True), ready=True).status is TopicStatus.READY


def test_a_topic_without_steps_is_new() -> None:
    assert topic().status is TopicStatus.NEW


def test_a_topic_with_steps_none_of_them_done_is_planned() -> None:
    assert topic(step(1, LEARN), step(2, PRACTICE)).status is TopicStatus.PLANNED


def test_a_topic_with_a_done_learn_step_and_no_done_practice_is_learning() -> None:
    steps = (step(1, LEARN, done=True), step(2, PRACTICE), step(3, CHECK))
    assert topic(*steps).status is TopicStatus.LEARNING


def test_a_done_check_step_alone_is_still_learning() -> None:
    steps = (step(1, LEARN), step(2, PRACTICE), step(3, CHECK, done=True))
    assert topic(*steps).status is TopicStatus.LEARNING


def test_a_topic_with_a_done_practice_step_is_practicing() -> None:
    steps = (step(1, LEARN), step(2, PRACTICE, done=True), step(3, CHECK))
    assert topic(*steps).status is TopicStatus.PRACTICING


def test_a_topic_with_every_step_done_but_not_marked_is_still_practicing() -> None:
    steps = (
        step(1, LEARN, done=True),
        step(2, PRACTICE, done=True),
        step(3, CHECK, done=True),
    )
    assert topic(*steps).status is TopicStatus.PRACTICING


def test_taking_ready_back_returns_the_status_from_the_steps() -> None:
    steps = (step(1, LEARN, done=True), step(2, PRACTICE), step(3, CHECK))
    ready = topic(*steps, ready=True)
    assert ready.status is TopicStatus.READY
    assert replace(ready, ready_at=None).status is TopicStatus.LEARNING
    assert replace(topic(ready=True), ready_at=None).status is TopicStatus.NEW


def test_pending_and_done_steps_keep_the_plan_order() -> None:
    steps = (
        step(1, LEARN, done=True),
        step(2, PRACTICE),
        step(3, CHECK, done=True),
        step(4, CHECK),
    )
    plan = topic(*steps)
    assert [s.number for s in plan.done] == [1, 3]
    assert [s.number for s in plan.pending] == [2, 4]


def test_minutes_left_are_the_minutes_of_the_pending_steps() -> None:
    plan = topic(
        step(1, LEARN, done=True, minutes=45),
        step(2, PRACTICE, minutes=90),
        step(3, CHECK, minutes=20),
    )
    assert plan.minutes_left == 110


def test_a_topic_without_pending_steps_has_no_minutes_left() -> None:
    assert topic(step(1, LEARN, done=True, minutes=45)).minutes_left == 0
    assert topic().minutes_left == 0


def test_a_topic_marked_ready_is_100_percent() -> None:
    assert topic(ready=True).percent == 100
    assert topic(step(1, LEARN), step(2, CHECK), ready=True).percent == 100


def test_a_topic_without_steps_that_is_not_ready_is_0_percent() -> None:
    assert topic().percent == 0


@pytest.mark.parametrize(
    ("total", "done", "percent"),
    [
        (6, 0, 0),
        (6, 1, 17),
        (6, 3, 50),
        (6, 5, 83),
        (6, 6, 100),
        (3, 1, 33),
        (3, 2, 67),
        (8, 1, 13),
        (8, 3, 38),
        (8, 5, 63),
        (12, 1, 8),
        (12, 11, 92),
    ],
)
def test_percent_is_the_share_of_done_steps_rounded_half_up(
    total: int, done: int, percent: int
) -> None:
    assert with_done(total, done).percent == percent


def test_readiness_of_a_job_without_topics_is_none() -> None:
    assert readiness([]) is None


def test_readiness_of_a_job_is_the_mean_of_its_topics() -> None:
    assert readiness([topic(ready=True), topic()]) == 50
    assert readiness([with_done(6, 3)]) == 50
    assert readiness([with_done(3, 1), with_done(3, 2), topic(ready=True)]) == 67


def test_readiness_rounds_half_up() -> None:
    # (17 + 0) / 2 = 8.5 → 9; round() дало б 8 (до парного).
    assert readiness([with_done(6, 1), topic()]) == 9
    # (17 + 100) / 2 = 58.5 → 59.
    assert readiness([with_done(6, 1), topic(ready=True)]) == 59
