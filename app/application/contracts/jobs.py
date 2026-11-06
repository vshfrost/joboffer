"""Команди й результати контексту jobs: примітиви (значення будує use case)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from application.contracts.applications import ApplicationData
from application.contracts.triage import TriageData
from domain.applications.application import ApplicationStatus
from domain.jobs.search import DEFAULT_LIMIT
from domain.profile.modes import WorkMode
from domain.triage.triage import TriageVerdict


@dataclass(frozen=True, slots=True, kw_only=True)
class JobInput:
    """Сирі значення з будь-якого транспорту; розбір і валідація — у домені."""

    text: str = ""
    url: str = ""
    title: str = ""
    company: str = ""


class AddOutcome(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    # Посилання LinkedIn на вакансію «потрібен текст»: опис дописано в наявну.
    TEXT_ADDED = "text_added"


@dataclass(frozen=True, slots=True)
class AddedJob:
    job_number: int
    outcome: AddOutcome

    @property
    def duplicate(self) -> bool:
        return self.outcome is AddOutcome.DUPLICATE


@dataclass(frozen=True, slots=True, kw_only=True)
class JobSearchInput:
    query: str = ""
    days: str = ""
    source: str = ""
    needs_text: bool = False
    dismissed: bool = False
    work_mode: str = ""
    triage_verdict: str = ""
    status: str = ""
    stage: str = ""
    hide_rejected: bool = False
    limit: int = DEFAULT_LIMIT


@dataclass(frozen=True, slots=True, kw_only=True)
class JobTabCountsData:
    in_progress: int
    applied_unreviewed: int
    needs_text: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class JobSummaryData:
    job_number: int
    source: str
    url: str | None
    title: str | None
    company: str | None
    created_at: datetime
    needs_text: bool
    dismissed: bool
    score: int | None = None
    filters_passed: bool | None = None
    work_mode: WorkMode | None = None
    triage_score: int | None = None
    triage_verdict: TriageVerdict | None = None
    triage_reason: str | None = None
    status: ApplicationStatus | None = None
    is_new: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class JobData:
    job_number: int
    source: str
    url: str | None
    title: str | None
    company: str | None
    location: str | None
    text: str | None
    created_at: datetime
    needs_text: bool
    dismissed_at: datetime | None
    dismiss_reason: str | None
    opened_at: datetime | None = None
    is_new: bool = False
    triage: TriageData | None = None
    application: ApplicationData | None = None
