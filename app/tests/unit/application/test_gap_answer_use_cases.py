"""Відповідь на прогалину аналізу: факти з чату, «немає досвіду», застарілість, дублі, ізоляція."""

from datetime import timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.actor import Actor
from application.contracts.analysis import (
    AnsweredGapData,
    GapAnswerInput,
    GapInput,
)
from application.contracts.facts import FactInput
from domain.facts.fact import FactKind, FactSource
from domain.shared.errors import InvalidValue, NotFound
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.unit.application.test_analysis_use_cases import World

GAPS = [
    GapInput(gap="No Go", question="Do you have Go experience? Where, how long?"),
    GapInput(gap="No Kubernetes", question="Have you run Kubernetes?"),
]
GO_FACT = FactInput(kind="experience", text="2 years of Go at Acme")


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def analysed(world: World, who: Actor | None = None) -> int:
    """Вакансія з аналізом: прогалини 1 «No Go» і 2 «No Kubernetes»."""
    actor = who or world.alice
    number = world.seed(actor)
    world.save(actor, number, gaps=GAPS)
    return number


def answer(
    world: World,
    number: int,
    gap: int,
    has_experience: bool,
    *facts: FactInput,
    who: Actor | None = None,
) -> AnsweredGapData:
    data = GapAnswerInput(has_experience=has_experience, facts=facts)
    return world.portal.call(
        world.analysis.answer_gap, who or world.alice, number, gap, data
    )


# --- «є досвід» ---------------------------------------------------------------


def test_experience_saves_the_facts_from_chat_confirmed_and_bound_to_the_job(
    world: World,
) -> None:
    number = analysed(world)

    result = answer(world, number, 1, True, GO_FACT)

    assert len(result.facts) == 1
    fact = result.facts[0]
    assert (fact.kind, fact.text) == (FactKind.EXPERIENCE, "2 years of Go at Acme")
    assert (fact.source, fact.confirmed, fact.job_id) == (
        FactSource.CHAT,
        True,
        number,
    )


def test_experience_closes_the_gap_with_the_fact_numbers(world: World) -> None:
    number = analysed(world)

    result = answer(world, number, 1, True, GO_FACT)

    assert (result.job_number, result.gap_number) == (number, 1)
    assert result.answer.gap == "No Go"
    assert result.answer.has_experience is True
    assert result.answer.fact_numbers == (result.facts[0].fact_number,)


def test_several_facts_are_all_linked_in_the_given_order(world: World) -> None:
    number = analysed(world)
    second = FactInput(kind="skill", text="Go")

    result = answer(world, number, 1, True, GO_FACT, second)

    assert [fact.text for fact in result.facts] == ["2 years of Go at Acme", "Go"]
    assert result.answer.fact_numbers == tuple(f.fact_number for f in result.facts)


def test_experience_makes_the_analysis_stale_from_the_answer_time(
    world: World,
) -> None:
    number = analysed(world)
    assert world.get(world.alice, number).stale_since is None
    world.clock.advance(timedelta(hours=1))

    answer(world, number, 1, True, GO_FACT)

    assert world.get(world.alice, number).stale_since == world.clock.now()


def test_experience_without_facts_is_refused_and_nothing_is_stored(
    world: World,
) -> None:
    number = analysed(world)

    with pytest.raises(InvalidValue) as error:
        answer(world, number, 1, True)

    assert error.value.field == "facts"
    assert world.prepare(world.alice, number).gap_answers == ()
    assert world.get(world.alice, number).stale_since is None


def test_an_invalid_fact_is_refused_with_its_position_and_nothing_is_stored(
    world: World,
) -> None:
    number = analysed(world)

    with pytest.raises(InvalidValue) as error:
        answer(world, number, 1, True, GO_FACT, FactInput(kind="skill", text="  "))

    assert error.value.field == "facts.1.text"
    assert error.value.message == "Факт 2: Факт не може бути порожнім."
    assert world.prepare(world.alice, number).gap_answers == ()
    assert world.get(world.alice, number).stale_since is None


# --- «немає досвіду» ----------------------------------------------------------


def test_no_experience_is_stored_without_facts(world: World) -> None:
    number = analysed(world)

    result = answer(world, number, 2, False)

    assert result.answer.gap == "No Kubernetes"
    assert (result.answer.has_experience, result.answer.fact_numbers) == (False, ())
    assert result.facts == ()


def test_no_experience_does_not_make_the_analysis_stale(world: World) -> None:
    number = analysed(world)
    world.clock.advance(timedelta(hours=1))

    answer(world, number, 2, False)

    assert world.get(world.alice, number).stale_since is None


def test_no_experience_with_facts_is_refused(world: World) -> None:
    number = analysed(world)

    with pytest.raises(InvalidValue) as error:
        answer(world, number, 2, False, GO_FACT)

    assert error.value.field == "facts"
    assert world.prepare(world.alice, number).gap_answers == ()


# --- не знайдено й ізоляція ---------------------------------------------------


def test_a_missing_job_is_not_found(world: World) -> None:
    with pytest.raises(NotFound) as error:
        answer(world, 9, 1, False)
    assert error.value.message == "Вакансію 9 не знайдено."


def test_a_job_without_an_analysis_is_not_found(world: World) -> None:
    number = world.seed(world.alice)
    with pytest.raises(NotFound) as error:
        answer(world, number, 1, False)
    assert error.value.message == f"Аналіз вакансії {number} не знайдено."


@pytest.mark.parametrize("gap_number", [0, 3, -1])
def test_a_missing_gap_is_not_found_and_nothing_is_stored(
    world: World, gap_number: int
) -> None:
    number = analysed(world)

    with pytest.raises(NotFound) as error:
        answer(world, number, gap_number, True, GO_FACT)

    assert (
        error.value.message == f"Прогалину {gap_number} вакансії {number} не знайдено."
    )
    assert world.prepare(world.alice, number).gap_answers == ()


def test_a_job_of_another_user_is_not_found(world: World) -> None:
    theirs = analysed(world, world.bob)

    with pytest.raises(NotFound):
        answer(world, theirs, 1, False)  # в Аліси вакансії з таким номером нема

    assert world.prepare(world.bob, theirs).gap_answers == ()


# --- дублі --------------------------------------------------------------------


def test_a_duplicate_fact_is_not_created_and_the_existing_one_is_linked(
    world: World,
) -> None:
    number = analysed(world)
    existing = world.fact(
        world.alice, "experience", "2 years of Go at Acme", confirmed=False
    )

    result = answer(
        world, number, 1, True, FactInput(kind="skill", text="2 YEARS of go at   Acme")
    )

    assert result.answer.fact_numbers == (existing,)
    assert [fact.fact_number for fact in result.facts] == [existing]
    assert result.facts[0].confirmed is True
    mine = [key for key in world.facts_store.facts if key[0] == world.alice.user_id]
    assert len(mine) == 1


def test_the_same_text_twice_in_one_answer_is_one_fact(world: World) -> None:
    number = analysed(world)

    result = answer(world, number, 1, True, GO_FACT, GO_FACT)

    assert len(result.facts) == 1
    assert result.answer.fact_numbers == (result.facts[0].fact_number,)


# --- повторна відповідь -------------------------------------------------------


def test_a_repeated_answer_replaces_the_previous_one(world: World) -> None:
    number = analysed(world)
    answer(world, number, 1, True, GO_FACT)

    answer(world, number, 1, False)

    answers = world.prepare(world.alice, number).gap_answers
    assert len(answers) == 1
    stored = answers[0]
    assert (stored.gap, stored.has_experience, stored.fact_numbers) == (
        "No Go",
        False,
        (),
    )


def test_a_no_can_become_a_yes(world: World) -> None:
    number = analysed(world)
    answer(world, number, 1, False)

    result = answer(world, number, 1, True, GO_FACT)

    answers = world.prepare(world.alice, number).gap_answers
    assert len(answers) == 1
    stored = answers[0]
    assert stored.has_experience is True
    assert stored.fact_numbers == (result.facts[0].fact_number,)


def test_answers_to_different_gaps_are_kept_separately(world: World) -> None:
    number = analysed(world)
    answer(world, number, 1, True, GO_FACT)
    answer(world, number, 2, False)

    stored = world.prepare(world.alice, number).gap_answers

    assert [(a.gap, a.has_experience) for a in stored] == [
        ("No Go", True),
        ("No Kubernetes", False),
    ]


# --- prepare_analysis ---------------------------------------------------------


def test_the_brief_of_a_job_without_answers_has_none(world: World) -> None:
    number = analysed(world)
    assert world.prepare(world.alice, number).gap_answers == ()


def test_the_brief_returns_the_no_answer_bound_to_the_gap_text(world: World) -> None:
    number = analysed(world)
    answer(world, number, 2, False)
    world.clock.advance(timedelta(days=1))
    world.save(
        world.alice, number, gaps=[GapInput(gap="no kubernetes ", question="K8s?")]
    )

    answers = world.prepare(world.alice, number).gap_answers
    assert len(answers) == 1
    stored = answers[0]

    assert (stored.gap, stored.has_experience) == ("No Kubernetes", False)


def test_the_brief_shows_only_the_answers_of_its_own_job_and_user(
    world: World,
) -> None:
    first = analysed(world)
    second = analysed(world)
    answer(world, second, 1, False)
    theirs = analysed(world, world.bob)
    answer(world, theirs, 1, False, who=world.bob)

    assert theirs == first
    assert world.prepare(world.alice, first).gap_answers == ()
    assert len(world.prepare(world.alice, second).gap_answers) == 1
