"""Вакансія, нова вакансія й рядок списку."""

from dataclasses import dataclass
from datetime import datetime
from typing import Self

from domain.applications.application import ApplicationStatus
from domain.jobs.ids import JobId
from domain.jobs.linkedin import linkedin_job_id, linkedin_job_url
from domain.jobs.urls import normalize_url
from domain.profile.modes import WorkMode
from domain.shared.errors import InvalidValue
from domain.shared.fingerprint import text_fingerprint
from domain.shared.problems import Problems
from domain.triage.triage import TriageVerdict

MAX_TEXT_LENGTH = 100_000
DEFAULT_SOURCE = "manual"
# Джерела, чиї вакансії до першого відкриття мають позначку «нове»; ручні й з алертів — ні.
NEW_BADGE_SOURCE_PREFIXES = ("ats:", "rss:")
# Номер вакансії зберігається в int4: більший за нього не існує.
MAX_JOB_NUMBER = 2**31 - 1


@dataclass(frozen=True, slots=True)
class NewJob:
    """Нова вакансія. Вставлена руками — обовʼязковий лише текст опису; з листа-алерту LinkedIn
    опису нема (`text` None — «потрібен текст»), є посилання, посада й компанія. Посилання
    LinkedIn зводиться до канонічного, його id — `linkedin_id`."""

    text: str | None
    url: str | None = None
    title: str | None = None
    company: str | None = None
    linkedin_id: str | None = None
    location: str | None = None
    source: str = DEFAULT_SOURCE

    @classmethod
    def parse(cls, *, text: str, url: str, title: str, company: str) -> Self:
        problems = Problems()
        text = text.strip()
        if not text:
            problems.add("text", "Встав текст опису вакансії.")
        elif len(text) > MAX_TEXT_LENGTH:
            problems.add("text", f"Опис задовгий: більше {MAX_TEXT_LENGTH} символів.")
        linkedin_id = linkedin_job_id(url)
        clean_url: str | None = None
        if linkedin_id is not None:
            clean_url = linkedin_job_url(linkedin_id)
        elif url.strip():
            try:
                clean_url = normalize_url(url)
            except InvalidValue as error:
                problems.add(error.field, error.message)
        problems.raise_if_any()
        return cls(
            text=text,
            url=clean_url,
            title=title.strip() or None,
            company=company.strip() or None,
            linkedin_id=linkedin_id,
        )

    @property
    def fingerprint(self) -> str | None:
        return None if self.text is None else text_fingerprint(self.text)


@dataclass(frozen=True, slots=True)
class Job:
    id: JobId
    # Номер у межах користувача (з 1): його бачать люди й MCP; `id` — внутрішній ключ.
    number: int
    source: str
    # None — «потрібен текст»: вакансія з листа-алерту, опису ще нема.
    text: str | None
    url: str | None
    title: str | None
    company: str | None
    created_at: datetime
    location: str | None = None
    # Коли й чому вакансію сховано («не цікаво»); None — не сховано.
    dismissed_at: datetime | None = None
    dismiss_reason: str | None = None
    # Коли вакансію вперше відкрили в деталях; None — ще не відкривали.
    opened_at: datetime | None = None

    @property
    def is_new(self) -> bool:
        return self.opened_at is None and self.source.startswith(
            NEW_BADGE_SOURCE_PREFIXES
        )

    @property
    def needs_text(self) -> bool:
        return self.text is None

    @property
    def dismissed(self) -> bool:
        return self.dismissed_at is not None


@dataclass(frozen=True, slots=True)
class JobSummary:
    """Рядок списку: без тексту опису."""

    number: int
    source: str
    url: str | None
    title: str | None
    company: str | None
    created_at: datetime
    needs_text: bool = False
    dismissed: bool = False
    # Повний аналіз; None — не проаналізовано.
    score: int | None = None
    filters_passed: bool | None = None
    work_mode: WorkMode | None = None
    # Швидкий тріаж (`domain.triage`); None — не тріажовано.
    triage_score: int | None = None
    triage_verdict: TriageVerdict | None = None
    triage_reason: str | None = None
    # Статус подачі; None — на вакансію не подавались.
    status: ApplicationStatus | None = None
    # Вакансія з джерела (`ats:` / `rss:`), яку ще не відкривали.
    is_new: bool = False
