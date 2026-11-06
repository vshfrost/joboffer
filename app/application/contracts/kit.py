"""Команди й результати пакета до інтерв'ю: примітиви (значення будує use case). Вакансія, тема й
факт — за номерами в межах користувача; версія пакета — окремо для кожної вакансії."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from application.contracts.analysis import AnalysisData
from application.contracts.facts import FactData
from application.contracts.jobs import JobData
from application.contracts.prep import TopicData


@dataclass(frozen=True, slots=True, kw_only=True)
class KitQuestionInput:
    """Сире питання з будь-якого транспорту; розбір і межі — у домені."""

    kind: str
    question: str
    topic_number: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StoryInput:
    """Сира STAR-історія з будь-якого транспорту; `fact_ids` — номери фактів."""

    title: str
    situation: str
    task: str
    action: str
    result: str
    fact_ids: Sequence[int] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class KitInput:
    """Сирий пакет з будь-якого транспорту; розбір і межі — у домені."""

    questions: Sequence[KitQuestionInput] = ()
    stories: Sequence[StoryInput] = ()
    company_questions: Sequence[str] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class KitQuestionData:
    kind: str
    question: str
    topic_number: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class StoryData:
    title: str
    situation: str
    task: str
    action: str
    result: str
    fact_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class KitData:
    """Версія пакета. `created_at` — момент збереження (UTC); день за Мадридом показує транспорт."""

    kit_number: int
    job_number: int
    version: int
    created_at: datetime
    questions: tuple[KitQuestionData, ...]
    stories: tuple[StoryData, ...]
    company_questions: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class KitBriefData:
    """Усе, що потрібно Claude для пакета під одну вакансію. Теми — вакансії, за пріоритетом;
    факти — лише підтверджені."""

    job: JobData
    analysis: AnalysisData | None
    topics: tuple[TopicData, ...]
    confirmed_facts: tuple[FactData, ...]
    rules: str
    previous: KitData | None
