"""Збережений аналіз показує відповідь на кожну прогалину: відкрита, закрита фактами чи «нема досвіду»."""

from datetime import timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.analysis import GapInput
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.unit.application.test_analysis_use_cases import World
from tests.unit.application.test_gap_answer_use_cases import GO_FACT, analysed, answer


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def test_a_gap_nobody_answered_has_no_answer(world: World) -> None:
    number = analysed(world)

    gaps = world.get(world.alice, number).gaps

    assert [(gap.gap, gap.answer) for gap in gaps] == [
        ("No Go", None),
        ("No Kubernetes", None),
    ]


def test_a_yes_answer_is_attached_to_its_gap_with_the_fact_numbers(
    world: World,
) -> None:
    number = analysed(world)
    answered = answer(world, number, 1, True, GO_FACT)

    first, second = world.get(world.alice, number).gaps

    assert first.answer is not None
    assert (first.answer.has_experience, first.answer.fact_numbers) == (
        True,
        (answered.facts[0].fact_number,),
    )
    assert second.answer is None


def test_a_no_answer_is_attached_to_its_gap_without_facts(world: World) -> None:
    number = analysed(world)
    answer(world, number, 2, False)

    first, second = world.get(world.alice, number).gaps

    assert first.answer is None
    assert second.answer is not None
    assert (second.answer.has_experience, second.answer.fact_numbers) == (False, ())


def test_a_repeated_answer_shows_only_the_latest_one(world: World) -> None:
    number = analysed(world)
    answer(world, number, 1, False)
    world.clock.advance(timedelta(minutes=1))
    answered = answer(world, number, 1, True, GO_FACT)

    first = world.get(world.alice, number).gaps[0]

    assert first.answer is not None
    assert (first.answer.has_experience, first.answer.fact_numbers) == (
        True,
        (answered.facts[0].fact_number,),
    )


def test_the_answer_follows_the_gap_text_after_a_new_analysis(world: World) -> None:
    number = analysed(world)
    answer(world, number, 2, False)
    world.clock.advance(timedelta(days=1))
    world.save(
        world.alice,
        number,
        gaps=[
            GapInput(gap="Rust", question="Written Rust?"),
            GapInput(gap="no kubernetes ", question="K8s?"),
        ],
    )

    rust, kubernetes = world.get(world.alice, number).gaps

    assert rust.answer is None
    assert kubernetes.answer is not None
    assert kubernetes.answer.has_experience is False


def test_answers_of_another_job_and_of_another_user_are_not_shown(
    world: World,
) -> None:
    first = analysed(world)
    second = analysed(world)
    answer(world, second, 1, False)
    theirs = analysed(world, world.bob)
    answer(world, theirs, 1, False, who=world.bob)

    assert theirs == first
    assert world.get(world.alice, first).gaps[0].answer is None
    assert world.get(world.bob, theirs).gaps[0].answer is not None
    assert world.get(world.alice, second).gaps[0].answer is not None
