"""Команди й результати контексту applications: примітиви (значення будує use case)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from domain.applications.application import (
    ApplicationChannel,
    ApplicationStatus,
    AtsPlatform,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationInput:
    """Сирі значення з будь-якого транспорту; розбір і валідація — у домені."""

    channel: str
    applied_on: str = ""
    ats: str = ""
    company_domains: Sequence[str] = ()
    company_emails: Sequence[str] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class CvVersionData:
    number: int
    saved_on: date
    coverage_percent: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationData:
    job_number: int
    status: ApplicationStatus
    applied_on: date
    channel: ApplicationChannel
    ats: AtsPlatform | None
    company_domains: tuple[str, ...]
    company_emails: tuple[str, ...]
    status_changed_at: datetime
    # Куди подачу можна рухати зараз: інтерфейс не дублює матрицю переходів.
    allowed_transitions: tuple[ApplicationStatus, ...]
    # None — «невідомо»: подача без CV чи зроблена до того, як подача почала пам'ятати версію.
    cv: CvVersionData | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CvFunnelRowData:
    """Одна версія CV у звіті: скільки подач, відповідей і інтервʼю. `cv_number` None — «невідомо»
    (подачі без CV і старі подачі); тоді дата й покриття теж None."""

    cv_number: int | None
    saved_on: date | None
    coverage_percent: int | None
    applications: int
    replies: int
    interviews: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CvFunnelData:
    rows: tuple[CvFunnelRowData, ...]
