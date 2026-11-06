"""Квіз: розбір питання й відповіді, коробки Leitner, порядок повторення, лічильники по темах.

Поведінка — як у v1 (`origin/main` `99a2007`, `core/domain/quiz.py`): коробки 1 / 2 / 4 / 8 / 16 днів,
прохідна оцінка 3, межі полів. «Сьогодні» передає викликач; Мадрид — у use case (див. BDD).
"""

import re
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from domain.prep.ids import QuestionId
from domain.prep.quiz import (
    BOX_DAYS,
    Answer,
    NewQuestion,
    PrepQuestion,
    QuizCount,
    Schedule,
    check_due_limit,
    due,
    first_schedule,
    next_schedule,
    quiz_counts,
)
from domain.shared.errors import InvalidValue

TODAY = date(2026, 3, 10)
NOW = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def parse(question: str = "What is an index?", *points: str) -> NewQuestion:
    return NewQuestion.parse(
        question=question, answer_points=points or ("Speeds up reads",)
    )


def stored(
    number: int, *, topic: int = 1, box: int = 1, due_on: date = TODAY
) -> PrepQuestion:
    return PrepQuestion(
        id=QuestionId(UUID(int=number)),
        number=number,
        topic_number=topic,
        topic_title=f"Тема {topic}",
        question=f"Question {number}?",
        answer_points=("Point",),
        box=box,
        due_on=due_on,
        created_at=NOW,
    )


def numbers(questions: list[PrepQuestion]) -> list[int]:
    return [question.number for question in questions]


# --- питання ---------------------------------------------------------------------------------


def test_a_question_keeps_its_text_and_key_points() -> None:
    question = parse("What is a join?", "Combines rows", "On a key")
    assert (question.question, question.answer_points) == (
        "What is a join?",
        ("Combines rows", "On a key"),
    )


def test_whitespace_in_a_question_and_in_points_collapses_to_one_line() -> None:
    question = parse("  What\n  is   a   join? ", " Combines\trows ")
    assert (question.question, question.answer_points) == (
        "What is a join?",
        ("Combines rows",),
    )


def test_an_empty_question_is_rejected() -> None:
    with pytest.raises(
        InvalidValue, match=re.escape("питання — від 1 до 500 символів.")
    ):
        parse(" \n ")


def test_a_question_of_500_characters_is_accepted_and_501_is_not() -> None:
    assert len(parse("q" * 500).question) == 500
    with pytest.raises(
        InvalidValue, match=re.escape("питання — від 1 до 500 символів.")
    ):
        parse("q" * 501)


def test_a_question_without_key_points_is_rejected() -> None:
    with pytest.raises(
        InvalidValue, match=re.escape("answer_points — від 1 до 8 пунктів.")
    ):
        NewQuestion.parse(question="What?", answer_points=[])


def test_eight_key_points_are_accepted_and_nine_are_not() -> None:
    assert len(parse("What?", *(f"p{n}" for n in range(8))).answer_points) == 8
    with pytest.raises(
        InvalidValue, match=re.escape("answer_points — від 1 до 8 пунктів.")
    ):
        parse("What?", *(f"p{n}" for n in range(9)))


def test_a_blank_key_point_is_rejected() -> None:
    with pytest.raises(
        InvalidValue, match=re.escape("кожен з answer_points — від 1 до 300 символів.")
    ):
        parse("What?", "fine", "  ")


def test_a_key_point_of_300_characters_is_accepted_and_301_is_not() -> None:
    assert len(parse("What?", "p" * 300).answer_points[0]) == 300
    with pytest.raises(
        InvalidValue, match=re.escape("кожен з answer_points — від 1 до 300 символів.")
    ):
        parse("What?", "p" * 301)


def test_questions_that_differ_only_in_case_and_spaces_have_one_fingerprint() -> None:
    assert (
        parse("What is   an INDEX?").fingerprint
        == parse("what is an index?").fingerprint
    )


def test_different_questions_have_different_fingerprints() -> None:
    assert (
        parse("What is an index?").fingerprint != parse("What is a join?").fingerprint
    )


# --- відповідь -------------------------------------------------------------------------------


@pytest.mark.parametrize("grade", [0, 1, 2, 3, 4, 5])
def test_every_grade_from_0_to_5_is_accepted(grade: int) -> None:
    assert Answer.parse(grade=grade, answer="a", feedback="f").grade == grade


@pytest.mark.parametrize("grade", [-1, 6])
def test_a_grade_outside_0_to_5_is_rejected(grade: int) -> None:
    with pytest.raises(InvalidValue, match=re.escape("Оцінка — ціле від 0 до 5.")):
        Answer.parse(grade=grade, answer="a", feedback="f")


def test_an_answer_and_feedback_are_trimmed_but_otherwise_kept() -> None:
    answer = Answer.parse(grade=4, answer="  Line 1\nLine 2 \n", feedback=" Good ")
    assert (answer.answer, answer.feedback) == ("Line 1\nLine 2", "Good")


def test_an_empty_answer_and_feedback_are_accepted() -> None:
    answer = Answer.parse(grade=0, answer="", feedback="")
    assert (answer.answer, answer.feedback) == ("", "")


def test_an_answer_of_4000_characters_is_accepted_and_4001_is_not() -> None:
    assert len(Answer.parse(grade=3, answer="a" * 4000, feedback="").answer) == 4000
    with pytest.raises(InvalidValue, match=re.escape("Відповідь — до 4000 символів.")):
        Answer.parse(grade=3, answer="a" * 4001, feedback="")


def test_feedback_of_2000_characters_is_accepted_and_2001_is_not() -> None:
    assert len(Answer.parse(grade=3, answer="", feedback="f" * 2000).feedback) == 2000
    with pytest.raises(InvalidValue, match=re.escape("Фідбек — до 2000 символів.")):
        Answer.parse(grade=3, answer="", feedback="f" * 2001)


# --- коробки Leitner -------------------------------------------------------------------------


def test_the_boxes_return_a_question_in_1_2_4_8_and_16_days() -> None:
    assert BOX_DAYS == (1, 2, 4, 8, 16)


def test_a_new_question_is_in_box_1_and_due_today() -> None:
    assert first_schedule(TODAY) == Schedule(1, TODAY)


@pytest.mark.parametrize(
    ("box", "grade", "new_box", "days"),
    [
        (1, 3, 2, 2),
        (1, 5, 2, 2),
        (2, 3, 3, 4),
        (3, 4, 4, 8),
        (4, 5, 5, 16),
        (5, 3, 5, 16),
        (5, 5, 5, 16),
    ],
)
def test_a_pass_moves_the_question_one_box_up_but_not_above_box_5(
    box: int, grade: int, new_box: int, days: int
) -> None:
    assert next_schedule(box, grade, TODAY) == Schedule(
        new_box, TODAY + timedelta(days=days)
    )


@pytest.mark.parametrize("box", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("grade", [0, 1, 2])
def test_a_fail_sends_the_question_back_to_box_1_for_tomorrow(
    box: int, grade: int
) -> None:
    assert next_schedule(box, grade, TODAY) == Schedule(1, TODAY + timedelta(days=1))


def test_grade_3_passes_and_grade_2_fails() -> None:
    assert next_schedule(2, 3, TODAY).box == 3
    assert next_schedule(2, 2, TODAY).box == 1


def test_the_next_review_counts_from_the_answer_day_across_a_month_end() -> None:
    assert next_schedule(4, 4, date(2026, 1, 25)) == Schedule(5, date(2026, 2, 10))


# --- що на повторенні ------------------------------------------------------------------------


def test_a_question_is_due_on_its_day_and_after_but_not_before() -> None:
    question = stored(1, due_on=TODAY)
    assert question.is_due(TODAY)
    assert question.is_due(TODAY + timedelta(days=1))
    assert not question.is_due(TODAY - timedelta(days=1))


def test_only_due_questions_are_returned() -> None:
    questions = [
        stored(1, due_on=TODAY + timedelta(days=1)),
        stored(2, due_on=TODAY),
        stored(3, due_on=TODAY - timedelta(days=5)),
    ]
    assert numbers(due(questions, TODAY)) == [3, 2]


def test_the_most_overdue_question_comes_first() -> None:
    questions = [
        stored(1, due_on=TODAY),
        stored(2, due_on=TODAY - timedelta(days=3)),
        stored(3, due_on=TODAY - timedelta(days=1)),
    ]
    assert numbers(due(questions, TODAY)) == [2, 3, 1]


def test_on_the_same_day_a_lower_box_comes_first() -> None:
    questions = [
        stored(1, box=4),
        stored(2, box=1),
        stored(3, box=3),
    ]
    assert numbers(due(questions, TODAY)) == [2, 3, 1]


def test_on_the_same_day_and_box_the_older_question_comes_first() -> None:
    questions = [stored(7), stored(3), stored(5)]
    assert numbers(due(questions, TODAY)) == [3, 5, 7]


def test_the_overdue_days_beat_the_box() -> None:
    questions = [
        stored(1, box=1, due_on=TODAY),
        stored(2, box=5, due_on=TODAY - timedelta(days=1)),
    ]
    assert numbers(due(questions, TODAY)) == [2, 1]


def test_nothing_is_due_when_there_are_no_questions() -> None:
    assert due([], TODAY) == []


@pytest.mark.parametrize("limit", [1, 10, 50])
def test_a_limit_from_1_to_50_is_accepted(limit: int) -> None:
    check_due_limit(limit)


@pytest.mark.parametrize("limit", [0, -1, 51])
def test_a_limit_outside_1_to_50_is_rejected(limit: int) -> None:
    with pytest.raises(InvalidValue, match=re.escape("limit — від 1 до 50.")):
        check_due_limit(limit)


# --- лічильники по темах ---------------------------------------------------------------------


def test_counts_show_all_and_due_questions_per_topic() -> None:
    questions = [
        stored(1, topic=1),
        stored(2, topic=1, due_on=TODAY + timedelta(days=2)),
        stored(3, topic=2, due_on=TODAY + timedelta(days=1)),
        stored(4, topic=1, due_on=TODAY - timedelta(days=1)),
    ]
    assert quiz_counts(questions, TODAY) == {
        1: QuizCount(total=3, due=2),
        2: QuizCount(total=1, due=0),
    }


def test_a_topic_without_questions_has_no_counts() -> None:
    assert quiz_counts([], TODAY) == {}
