"""Що показати в списку вакансій."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Self

from domain.applications.application import ApplicationStatus, parse_status_filter
from domain.profile.modes import WorkMode
from domain.shared.errors import InvalidValue
from domain.shared.problems import Problems
from domain.triage.triage import TriageVerdict

MAX_QUERY_LENGTH = 200
MAX_DAYS = 3650
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class JobStage(StrEnum):
    """Етап вакансії для табів вебу (сховані й відмови поза етапами).

    open — є текст, немає подачі й взаємодії (тріаж і відкриття деталей — не взаємодія);
    in_progress — немає подачі, але є аналіз, документ, interview kit, тема підготовки чи факт
    вакансії, плюс подачі зі статусом withdrawn; applied — активна подача (applied … offer).
    """

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    APPLIED = "applied"


@dataclass(frozen=True, slots=True)
class JobTabCounts:
    """Лічильники табів вебу: не залежать від фільтрів запиту й від ліміту списку."""

    in_progress: int
    # Скільки вакансій мають нерозібраний лист (`reviewed_at IS NULL`) до активної подачі.
    applied_unreviewed: int
    # Є не схована вакансія без тексту (відмови не рахуються — їх у вебі нема).
    needs_text: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class JobSearchDraft:
    """Сирі значення фільтрів з будь-якого транспорту."""

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


def _parse_stage(raw: str, problems: Problems) -> JobStage | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return JobStage(cleaned)
    except ValueError:
        allowed = ", ".join(item.value for item in JobStage)
        problems.add("stage", f"Етап — один з: {allowed}.")
        return None


@dataclass(frozen=True, slots=True)
class JobSearch:
    """None = без обмеження. `dismissed` False — лише не сховані, True — лише сховані.
    `stage` — етап для табів вебу; `hide_rejected` ховає вакансії з відмовою (лише веб-список)."""

    query: str | None = None
    since: datetime | None = None
    source: str | None = None
    needs_text: bool = False
    dismissed: bool = False
    work_mode: WorkMode | None = None
    triage_verdict: TriageVerdict | None = None
    statuses: frozenset[ApplicationStatus] | None = None
    stage: JobStage | None = None
    hide_rejected: bool = False
    limit: int = DEFAULT_LIMIT

    @classmethod
    def parse(cls, draft: JobSearchDraft, now: datetime) -> Self:
        problems = Problems()
        query = " ".join(draft.query.split())
        if len(query) > MAX_QUERY_LENGTH:
            problems.add(
                "query", f"Запит задовгий: більше {MAX_QUERY_LENGTH} символів."
            )
        since: datetime | None = None
        days = draft.days.strip()
        if days:
            if days.isascii() and days.isdigit() and 1 <= int(days) <= MAX_DAYS:
                since = now - timedelta(days=int(days))
            else:
                problems.add("days", f"Свіжість — ціле число днів від 1 до {MAX_DAYS}.")
        work_mode: WorkMode | None = None
        if draft.work_mode.strip():
            try:
                work_mode = WorkMode(draft.work_mode.strip())
            except ValueError:
                problems.add("work_mode", "Невідомий формат роботи.")
        verdict: TriageVerdict | None = None
        if draft.triage_verdict.strip():
            try:
                verdict = TriageVerdict(draft.triage_verdict.strip())
            except ValueError:
                problems.add("triage_verdict", "Невідомий вердикт тріажу.")
        statuses: frozenset[ApplicationStatus] | None = None
        if draft.status.strip():
            try:
                statuses = parse_status_filter(draft.status)
            except InvalidValue as error:
                problems.add("status", error.message)
        stage = _parse_stage(draft.stage, problems)
        if not 1 <= draft.limit <= MAX_LIMIT:
            problems.add("limit", f"Ліміт — від 1 до {MAX_LIMIT}.")
        problems.raise_if_any()
        return cls(
            query=query or None,
            since=since,
            source=draft.source.strip() or None,
            needs_text=draft.needs_text,
            dismissed=draft.dismissed,
            work_mode=work_mode,
            triage_verdict=verdict,
            statuses=statuses,
            stage=stage,
            hide_rejected=draft.hide_rejected,
            limit=draft.limit,
        )
