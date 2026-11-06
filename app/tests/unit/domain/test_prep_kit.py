"""Пакет до інтерв'ю: розбір питань, STAR-історій і питань до компанії, межі кількості, факти й теми.

Поведінка — як у v1 (`origin/main` `99a2007`, `core/domain/interview.py`): межі 5–20 / 3–6 / 3–8,
довжини 500 / 120 / 1000, 1–10 фактів в історії, повтори фактів зводяться. Підтвердженість фактів
і наявність тем перевіряє use case (див. BDD): тут лише форма.
"""

import re

import pytest

from domain.prep.kit import (
    InterviewKit,
    KitQuestion,
    KitQuestionKind,
    StarStory,
    parse_company_question,
)
from domain.shared.errors import InvalidValue

PARTS = ("situation", "task", "action", "result")


def question(
    text: str = "What is an index?",
    *,
    kind: str = "technical",
    topic: int | None = None,
) -> KitQuestion:
    return KitQuestion.parse(kind=kind, question=text, topic_number=topic)


def story(
    title: str = "Migration",
    facts: tuple[int, ...] = (1,),
    *,
    situation: str = "Text of situation",
    task: str = "Text of task",
    action: str = "Text of action",
    result: str = "Text of result",
) -> StarStory:
    return StarStory.parse(
        title=title,
        situation=situation,
        task=task,
        action=action,
        result=result,
        fact_ids=facts,
    )


def story_with(part: str, text: str) -> StarStory:
    """Історія, де лише одна зі STAR-частин має значення `text`."""
    values = {name: f"Text of {name}" for name in PARTS} | {part: text}
    return StarStory.parse(title="Migration", fact_ids=(1,), **values)


def kit(
    questions: int = 5,
    stories: int = 3,
    company: int = 3,
    *,
    topics: tuple[int | None, ...] = (),
    facts: tuple[int, ...] = (1,),
) -> InterviewKit:
    return InterviewKit(
        questions=tuple(
            question(f"Question {n}?", topic=topics[n] if n < len(topics) else None)
            for n in range(questions)
        ),
        stories=tuple(story(f"Story {n}", facts) for n in range(stories)),
        company_questions=tuple(f"Company question {n}?" for n in range(company)),
    )


def rejected(message: str) -> pytest.RaisesExc[InvalidValue]:
    return pytest.raises(InvalidValue, match=f"^{re.escape(message)}$")


# --- питання ---------------------------------------------------------------------------------


def test_a_technical_question_keeps_its_text_and_topic() -> None:
    parsed = question("What is an index?", kind="technical", topic=3)
    assert (parsed.kind, parsed.question, parsed.topic_number) == (
        KitQuestionKind.TECHNICAL,
        "What is an index?",
        3,
    )


def test_a_behavioral_question_without_a_topic_has_none() -> None:
    parsed = question("Tell me about a conflict.", kind="behavioral")
    assert (parsed.kind, parsed.topic_number) == (KitQuestionKind.BEHAVIORAL, None)


def test_the_kind_ignores_case_and_surrounding_spaces() -> None:
    assert question(kind=" Behavioral ").kind is KitQuestionKind.BEHAVIORAL


def test_an_unknown_kind_is_rejected_with_the_allowed_ones() -> None:
    with rejected("kind 'senior' — допустимо technical, behavioral."):
        question(kind="senior")


def test_whitespace_in_a_question_collapses_to_one_line() -> None:
    assert question("  What\n  is   an\tindex? ").question == "What is an index?"


def test_an_empty_question_is_rejected() -> None:
    with rejected("питання — від 1 до 500 символів."):
        question(" \n ")


def test_a_question_of_500_characters_is_accepted_and_501_is_not() -> None:
    assert len(question("q" * 500).question) == 500
    with rejected("питання — від 1 до 500 символів."):
        question("q" * 501)


# --- STAR-історії ----------------------------------------------------------------------------


def test_a_story_keeps_its_title_parts_and_facts() -> None:
    parsed = story("Migration", (4, 2), situation="S", task="T", action="A", result="R")
    assert (
        parsed.title,
        parsed.situation,
        parsed.task,
        parsed.action,
        parsed.result,
        parsed.fact_ids,
    ) == ("Migration", "S", "T", "A", "R", (4, 2))


def test_whitespace_in_a_story_collapses_to_one_line() -> None:
    parsed = story("  Big\n migration ", situation=" Old\n  system ")
    assert (parsed.title, parsed.situation) == ("Big migration", "Old system")


def test_repeated_facts_in_a_story_collapse_keeping_the_first_order() -> None:
    assert story(facts=(5, 2, 5, 2, 9)).fact_ids == (5, 2, 9)


def test_a_story_without_facts_is_rejected() -> None:
    with rejected(
        "fact_ids — від 1 до 10: історія стоїть лише на підтверджених фактах."
    ):
        story(facts=())


def test_a_story_on_ten_facts_is_accepted_and_eleven_are_not() -> None:
    assert len(story(facts=tuple(range(1, 11))).fact_ids) == 10
    with rejected(
        "fact_ids — від 1 до 10: історія стоїть лише на підтверджених фактах."
    ):
        story(facts=tuple(range(1, 12)))


def test_eleven_facts_with_a_repeat_count_as_ten() -> None:
    assert len(story(facts=(*range(1, 11), 1)).fact_ids) == 10


@pytest.mark.parametrize("part", PARTS)
def test_each_star_part_of_1000_characters_is_accepted_and_1001_is_not(
    part: str,
) -> None:
    assert len(getattr(story_with(part, "x" * 1000), part)) == 1000
    with rejected(f"{part} — від 1 до 1000 символів."):
        story_with(part, "x" * 1001)


@pytest.mark.parametrize("part", PARTS)
def test_an_empty_star_part_is_rejected(part: str) -> None:
    with rejected(f"{part} — від 1 до 1000 символів."):
        story_with(part, "  ")


def test_a_title_of_120_characters_is_accepted_and_121_is_not() -> None:
    assert len(story("t" * 120).title) == 120
    with rejected("назва — від 1 до 120 символів."):
        story("t" * 121)


def test_an_empty_title_is_rejected() -> None:
    with rejected("назва — від 1 до 120 символів."):
        story(" ")


# --- питання до компанії ---------------------------------------------------------------------


def test_a_company_question_collapses_whitespace() -> None:
    assert parse_company_question(" How is\n the  team? ") == "How is the team?"


def test_a_company_question_of_500_characters_is_accepted_and_501_is_not() -> None:
    assert len(parse_company_question("c" * 500)) == 500
    with rejected("питання до компанії — від 1 до 500 символів."):
        parse_company_question("c" * 501)


def test_an_empty_company_question_is_rejected() -> None:
    with rejected("питання до компанії — від 1 до 500 символів."):
        parse_company_question("")


# --- межі кількості --------------------------------------------------------------------------


@pytest.mark.parametrize("count", [5, 12, 20])
def test_five_to_twenty_questions_are_accepted(count: int) -> None:
    assert len(kit(questions=count).questions) == count


@pytest.mark.parametrize("count", [0, 4, 21])
def test_fewer_than_five_or_more_than_twenty_questions_are_rejected(
    count: int,
) -> None:
    with rejected(f"questions: {count} — треба від 5 до 20."):
        kit(questions=count)


@pytest.mark.parametrize("count", [3, 4, 6])
def test_three_to_six_stories_are_accepted(count: int) -> None:
    assert len(kit(stories=count).stories) == count


@pytest.mark.parametrize("count", [0, 2, 7])
def test_fewer_than_three_or_more_than_six_stories_are_rejected(count: int) -> None:
    with rejected(f"stories: {count} — треба від 3 до 6."):
        kit(stories=count)


@pytest.mark.parametrize("count", [3, 5, 8])
def test_three_to_eight_company_questions_are_accepted(count: int) -> None:
    assert len(kit(company=count).company_questions) == count


@pytest.mark.parametrize("count", [0, 2, 9])
def test_fewer_than_three_or_more_than_eight_company_questions_are_rejected(
    count: int,
) -> None:
    with rejected(f"company_questions: {count} — треба від 3 до 8."):
        kit(company=count)


def test_with_several_counts_wrong_the_questions_are_reported_first() -> None:
    with rejected("questions: 2 — треба від 5 до 20."):
        kit(questions=2, stories=1, company=1)


def test_with_questions_fine_the_stories_are_reported_before_the_company_questions() -> (
    None
):
    with rejected("stories: 1 — треба від 3 до 6."):
        kit(stories=1, company=1)


# --- факти й теми пакета ---------------------------------------------------------------------


def test_the_kit_facts_are_all_the_facts_of_its_stories_once() -> None:
    packed = InterviewKit(
        questions=kit().questions,
        stories=(story(facts=(1, 2)), story(facts=(2, 3)), story(facts=(7,))),
        company_questions=kit().company_questions,
    )
    assert packed.fact_ids == frozenset({1, 2, 3, 7})


def test_the_kit_topics_are_the_distinct_topics_of_its_questions() -> None:
    assert kit(questions=6, topics=(2, None, 2, 5)).topic_numbers == frozenset({2, 5})


def test_a_kit_without_topics_has_no_topic_numbers() -> None:
    assert kit().topic_numbers == frozenset()
