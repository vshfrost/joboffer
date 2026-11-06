"""Квіз підготовки до інтерв'ю: питання англійською, як на співбесіді, і повторення за Leitner.

Питання пише й оцінює Claude у чаті; сервер зберігає їх з історією відповідей і рахує, коли
питання повернеться. Коробки 1–5 повертають питання через 1 / 2 / 4 / 8 / 16 днів; «сьогодні»
розкладу — за Мадридом. Помилки розбору питання — без номера: його додає use case, що знає позицію.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Self

from domain.prep.ids import QuestionId
from domain.shared.errors import InvalidValue
from domain.shared.fingerprint import text_fingerprint
from domain.shared.text import one_line

MAX_QUESTION_LENGTH = 500
MAX_POINTS = 8
MAX_POINT_LENGTH = 300
MAX_QUESTIONS_PER_SAVE = 20
MAX_ANSWER_LENGTH = 4000
MAX_FEEDBACK_LENGTH = 2000
DEFAULT_DUE_LIMIT = 10
MAX_DUE_LIMIT = 50
MAX_GRADE = 5
PASS_GRADE = 3
# Коробка N (1–5) → через скільки днів питання повертається.
BOX_DAYS = (1, 2, 4, 8, 16)


@dataclass(frozen=True, slots=True)
class NewQuestion:
    question: str
    answer_points: tuple[str, ...]

    @classmethod
    def parse(cls, *, question: str, answer_points: Sequence[str]) -> Self:
        question = one_line(question)
        if not question or len(question) > MAX_QUESTION_LENGTH:
            raise InvalidValue(
                "question", f"питання — від 1 до {MAX_QUESTION_LENGTH} символів."
            )
        points = tuple(one_line(point) for point in answer_points)
        if not 1 <= len(points) <= MAX_POINTS:
            raise InvalidValue(
                "answer_points", f"answer_points — від 1 до {MAX_POINTS} пунктів."
            )
        if any(not point or len(point) > MAX_POINT_LENGTH for point in points):
            raise InvalidValue(
                "answer_points",
                f"кожен з answer_points — від 1 до {MAX_POINT_LENGTH} символів.",
            )
        return cls(question, points)

    @property
    def fingerprint(self) -> str:
        """Дубль у темі = те саме питання без урахування пробілів і регістру."""
        return text_fingerprint(self.question)


@dataclass(frozen=True, slots=True)
class Answer:
    """Відповідь користувача, оцінка й фідбек Claude — рядок в історії спроб."""

    grade: int
    answer: str
    feedback: str

    @classmethod
    def parse(cls, *, grade: int, answer: str, feedback: str) -> Self:
        if not 0 <= grade <= MAX_GRADE:
            raise InvalidValue("grade", f"Оцінка — ціле від 0 до {MAX_GRADE}.")
        answer = answer.strip()
        if len(answer) > MAX_ANSWER_LENGTH:
            raise InvalidValue(
                "answer", f"Відповідь — до {MAX_ANSWER_LENGTH} символів."
            )
        feedback = feedback.strip()
        if len(feedback) > MAX_FEEDBACK_LENGTH:
            raise InvalidValue(
                "feedback", f"Фідбек — до {MAX_FEEDBACK_LENGTH} символів."
            )
        return cls(grade, answer, feedback)


@dataclass(frozen=True, slots=True)
class PastAnswer:
    """Спроба в історії питання; `box` — коробка питання після неї."""

    grade: int
    answer: str
    feedback: str
    box: int
    answered_at: datetime


@dataclass(frozen=True, slots=True)
class Schedule:
    """Коробка Leitner (1–5) і день, коли питання знову на повторенні."""

    box: int
    due_on: date


def first_schedule(today: date) -> Schedule:
    """Нове питання — у першій коробці й на повторенні одразу."""
    return Schedule(1, today)


def next_schedule(box: int, grade: int, today: date) -> Schedule:
    """Оцінка від PASS_GRADE — коробка вгору (не вище останньої), нижче — назад у першу;
    питання повертається через стільки днів, скільки дає нова коробка."""
    box = min(box + 1, len(BOX_DAYS)) if grade >= PASS_GRADE else 1
    return Schedule(box, today + timedelta(days=BOX_DAYS[box - 1]))


def check_due_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_DUE_LIMIT:
        raise InvalidValue("limit", f"limit — від 1 до {MAX_DUE_LIMIT}.")


@dataclass(frozen=True, slots=True)
class PrepQuestion:
    """Збережене питання. `number` — номер у межах користувача, `id` — внутрішній ключ,
    `topic_number` — номер теми користувача."""

    id: QuestionId
    number: int
    topic_number: int
    topic_title: str
    question: str
    answer_points: tuple[str, ...]
    box: int
    due_on: date
    created_at: datetime

    def is_due(self, today: date) -> bool:
        return self.due_on <= today


def due(questions: Iterable[PrepQuestion], today: date) -> list[PrepQuestion]:
    """Питання на повторення: давніше прострочені першими, далі нижчі коробки (слабші)."""
    return sorted(
        (question for question in questions if question.is_due(today)),
        key=lambda question: (question.due_on, question.box, question.number),
    )


@dataclass(frozen=True, slots=True)
class QuizCount:
    total: int = 0
    due: int = 0


def quiz_counts(questions: Iterable[PrepQuestion], today: date) -> dict[int, QuizCount]:
    """Скільки питань у кожній темі (за номером теми) і скільки з них на повторенні сьогодні."""
    counts: dict[int, QuizCount] = {}
    for question in questions:
        count = counts.get(question.topic_number, QuizCount())
        counts[question.topic_number] = QuizCount(
            count.total + 1, count.due + int(question.is_due(today))
        )
    return counts
