"""Команди й результати контексту analysis: примітиви (значення будує use case)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from application.contracts.facts import FactData, FactInput
from application.contracts.jobs import JobData
from application.contracts.profile import ProfileData
from domain.profile.modes import Seniority, WorkMode


@dataclass(frozen=True, slots=True, kw_only=True)
class GapInput:
    """Прогалина з транспорту: текст і питання користувачу про його досвід."""

    gap: str
    question: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GapAnswerData:
    """Збережена відповідь; `gap` — текст прогалини, до якого вона прив'язана."""

    gap: str
    has_experience: bool
    fact_numbers: tuple[int, ...]
    answered_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class GapData:
    """Збережена прогалина; `number` — порядковий номер у аналізі, з 1. `question` null — старий формат."""

    number: int
    gap: str
    question: str | None
    answer: GapAnswerData | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class KeywordFactsData:
    """Ключове слово аналізу й номери фактів, що його підтверджують."""

    keyword: str
    fact_numbers: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisInput:
    """Сирі значення з будь-якого транспорту; рядки й списки чистяться в домені."""

    score: int
    summary: str
    must_have: Sequence[str] = ()
    nice_to_have: Sequence[str] = ()
    keywords: Sequence[str] = ()
    seniority: str = ""
    work_mode: str = ""
    location: str = ""
    languages: Sequence[str] = ()
    salary_min_eur: int | None = None
    salary_max_eur: int | None = None
    relocation: bool | None = None
    reasons: Sequence[str] = field(default=())
    gaps: Sequence[str | GapInput] = field(default=())
    # Ключове слово → номери фактів під ним; None — карти нема.
    keyword_facts: Mapping[str, Sequence[int]] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisData:
    """Збережений аналіз вакансії; `stale_since` — з якого дня профіль змінено після аналізу."""

    job_number: int
    score: int
    summary: str
    must_have: tuple[str, ...]
    nice_to_have: tuple[str, ...]
    keywords: tuple[str, ...]
    seniority: Seniority | None
    work_mode: WorkMode | None
    location: str | None
    languages: tuple[str, ...]
    salary_min_eur: int | None
    salary_max_eur: int | None
    relocation: bool | None
    reasons: tuple[str, ...]
    gaps: tuple[GapData, ...]
    filters_passed: bool
    flags: tuple[str, ...]
    updated_at: datetime
    stale_since: datetime | None = None
    keyword_facts: tuple[KeywordFactsData, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GapAnswerInput:
    """Відповідь на прогалину з транспорту: факти — лише коли користувач схвалив їх формулювання."""

    has_experience: bool
    facts: Sequence[FactInput] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class AnsweredGapData:
    """Результат `answer_gap`: відповідь і факти, що її закривають (нові чи наявні)."""

    job_number: int
    gap_number: int
    answer: GapAnswerData
    facts: tuple[FactData, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisBriefData:
    """Усе, що потрібно Claude для аналізу однієї вакансії."""

    job: JobData
    profile: ProfileData
    confirmed_facts: tuple[FactData, ...]
    rubric: str
    previous: AnalysisData | None
    # Відповіді користувача на прогалини цієї вакансії: щоб не питати про те саме вдруге.
    gap_answers: tuple[GapAnswerData, ...] = ()
