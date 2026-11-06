"""Команди й результати контексту triage: примітиви (значення будує use case)."""

from dataclasses import dataclass
from datetime import datetime

from application.contracts.profile import ProfileData
from domain.triage.brief import TextScope
from domain.triage.triage import Triage, TriageSource, TriageVerdict


@dataclass(frozen=True, slots=True, kw_only=True)
class TriageInput:
    """Сирий елемент пачки з будь-якого транспорту; валідація — у домені."""

    job_number: int
    score: int
    verdict: str
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TriageCandidateData:
    """Вакансія для тріажу: секції вимог або весь текст (недовірені дані); `text_scope` каже, що саме."""

    job_number: int
    title: str | None
    company: str | None
    source: str
    location: str | None
    text: str
    text_scope: TextScope


@dataclass(frozen=True, slots=True, kw_only=True)
class TriageFactData:
    """Підтверджений факт у стислому вигляді: вид і текст."""

    kind: str
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TriageBriefData:
    jobs: tuple[TriageCandidateData, ...]
    # Скільки вакансій чекає на тріаж усього (разом із цією пачкою).
    pending: int
    # Спільний контекст (профіль, правила, підтверджені факти); `None` — не запитано.
    profile: ProfileData | None
    rules: str | None
    facts: tuple[TriageFactData, ...] | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TriageData:
    """Збережений тріаж вакансії."""

    job_number: int
    score: int
    verdict: TriageVerdict
    reason: str
    triaged_at: datetime
    source: TriageSource = TriageSource.AGENT


@dataclass(frozen=True, slots=True, kw_only=True)
class SavedTriageData:
    saved: tuple[TriageData, ...]

    def with_verdict(self, verdict: TriageVerdict) -> list[int]:
        return [item.job_number for item in self.saved if item.verdict is verdict]


def triage_data(triage: Triage) -> TriageData:
    return TriageData(
        job_number=triage.job_number,
        score=triage.score,
        verdict=triage.verdict,
        reason=triage.reason,
        triaged_at=triage.triaged_at,
        source=triage.source,
    )
