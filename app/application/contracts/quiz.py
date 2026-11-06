"""Команди й результати квізу: примітиви (значення будує use case). Питання й тема — за номерами
в межах користувача; ключ оцінки (`answer_points`) є лише у питаннях для квізу."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from application.contracts.prep import TopicDetailData


@dataclass(frozen=True, slots=True, kw_only=True)
class QuestionInput:
    """Сире питання з будь-якого транспорту; розбір і межі — у домені."""

    question: str
    answer_points: Sequence[str] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class AnswerInput:
    """Сира відповідь користувача з оцінкою й фідбеком Claude."""

    grade: int
    answer: str = ""
    feedback: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class QuestionData:
    """Питання з розкладом. `due_on` — день повторення за Мадридом. Без ключа оцінки."""

    question_number: int
    topic_number: int
    topic_title: str
    question: str
    box: int
    due_on: date


@dataclass(frozen=True, slots=True, kw_only=True)
class DueQuestionData:
    """Питання на повторення разом із ключем оцінки: його бачить лише Claude, що веде квіз."""

    question: QuestionData
    answer_points: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class QuestionsBriefData:
    """Тема з планом і нотатками, її наявні питання + правила питань для Claude."""

    detail: TopicDetailData
    questions: tuple[QuestionData, ...]
    rules: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SavedQuestionsData:
    """Додані питання і тексти пропущених дублів (у темі чи раніше в тому ж запиті)."""

    added: tuple[QuestionData, ...]
    skipped: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class DueQuizData:
    """Перші `limit` питань на повторення, скільки їх усього на сьогодні, і правила квізу."""

    questions: tuple[DueQuestionData, ...]
    total: int
    rules: str


@dataclass(frozen=True, slots=True, kw_only=True)
class QuizCountData:
    """Питань у темі і скільки з них на повторенні сьогодні (за Мадридом)."""

    total: int
    due: int
