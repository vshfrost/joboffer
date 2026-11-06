"""Пакет до інтерв'ю під вакансію: ймовірні питання, STAR-історії з підтверджених фактів і питання
користувача до компанії. Пише Claude, сервер перевіряє межі й зберігає версії.

Помилки розбору елемента — без номера: його додає use case, що знає позицію. Підтвердженість
фактів і наявність тем перевіряє use case (факти й теми — дані користувача).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self

from domain.prep.ids import KitId
from domain.shared.errors import InvalidValue
from domain.shared.text import one_line

MIN_QUESTIONS = 5
MAX_QUESTIONS = 20
MIN_STORIES = 3
MAX_STORIES = 6
MIN_COMPANY_QUESTIONS = 3
MAX_COMPANY_QUESTIONS = 8
MAX_QUESTION_LENGTH = 500
MAX_STORY_TITLE_LENGTH = 120
MAX_STAR_PART_LENGTH = 1000
MAX_STORY_FACT_IDS = 10


class KitQuestionKind(StrEnum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"


@dataclass(frozen=True, slots=True)
class KitQuestion:
    kind: KitQuestionKind
    question: str
    # Номер теми підготовки, що готує відповідь; None — нема.
    topic_number: int | None = None

    @classmethod
    def parse(cls, *, kind: str, question: str, topic_number: int | None) -> Self:
        try:
            question_kind = KitQuestionKind(kind.strip().lower())
        except ValueError as error:
            allowed = ", ".join(member.value for member in KitQuestionKind)
            raise InvalidValue(
                "kind", f"kind {kind!r} — допустимо {allowed}."
            ) from error
        return cls(
            question_kind,
            _text("question", "питання", question, MAX_QUESTION_LENGTH),
            topic_number,
        )


@dataclass(frozen=True, slots=True)
class StarStory:
    title: str
    situation: str
    task: str
    action: str
    result: str
    fact_ids: tuple[int, ...]

    @classmethod
    def parse(  # noqa: PLR0913
        cls,
        *,
        title: str,
        situation: str,
        task: str,
        action: str,
        result: str,
        fact_ids: Sequence[int],
    ) -> Self:
        facts = tuple(dict.fromkeys(fact_ids))
        if not 1 <= len(facts) <= MAX_STORY_FACT_IDS:
            raise InvalidValue(
                "fact_ids",
                f"fact_ids — від 1 до {MAX_STORY_FACT_IDS}: історія стоїть лише на "
                "підтверджених фактах.",
            )
        return cls(
            situation=_text("situation", "situation", situation, MAX_STAR_PART_LENGTH),
            task=_text("task", "task", task, MAX_STAR_PART_LENGTH),
            action=_text("action", "action", action, MAX_STAR_PART_LENGTH),
            result=_text("result", "result", result, MAX_STAR_PART_LENGTH),
            title=_text("title", "назва", title, MAX_STORY_TITLE_LENGTH),
            fact_ids=facts,
        )


def parse_company_question(question: str) -> str:
    return _text(
        "company_questions", "питання до компанії", question, MAX_QUESTION_LENGTH
    )


@dataclass(frozen=True, slots=True)
class InterviewKit:
    questions: tuple[KitQuestion, ...]
    stories: tuple[StarStory, ...]
    company_questions: tuple[str, ...]

    def __post_init__(self) -> None:
        for name, items, low, high in (
            ("questions", self.questions, MIN_QUESTIONS, MAX_QUESTIONS),
            ("stories", self.stories, MIN_STORIES, MAX_STORIES),
            (
                "company_questions",
                self.company_questions,
                MIN_COMPANY_QUESTIONS,
                MAX_COMPANY_QUESTIONS,
            ),
        ):
            if not low <= len(items) <= high:
                raise InvalidValue(
                    name, f"{name}: {len(items)} — треба від {low} до {high}."
                )

    @property
    def fact_ids(self) -> frozenset[int]:
        """Факти, на яких стоять історії."""
        return frozenset(number for story in self.stories for number in story.fact_ids)

    @property
    def topic_numbers(self) -> frozenset[int]:
        """Теми, на які посилаються питання."""
        return frozenset(
            question.topic_number
            for question in self.questions
            if question.topic_number is not None
        )


@dataclass(frozen=True, slots=True)
class KitVersion:
    """Збережена версія пакета під вакансію. `number` — номер у межах користувача, `id` —
    внутрішній ключ, `job_number` — номер вакансії користувача, `version` — з 1 окремо для
    кожної вакансії."""

    id: KitId
    number: int
    job_number: int
    version: int
    kit: InterviewKit
    created_at: datetime


def _text(field: str, label: str, value: str, limit: int) -> str:
    value = one_line(value)
    if not value or len(value) > limit:
        raise InvalidValue(field, f"{label} — від 1 до {limit} символів.")
    return value
