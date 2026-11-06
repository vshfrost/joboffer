"""Воронка подач за версіями CV: скільки подач, відповідей і інтервʼю на кожну версію.

Відповідь — подача зараз у replied, interview чи offer; інтервʼю — в interview чи offer.
Відмова й відкликання (rejected, withdrawn) рахуються лише як подачі: історії статусів
подача не тримає, тож відмова після відповіді вже не відрізняється від відмови без неї.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from domain.applications.application import (
    Application,
    ApplicationStatus,
    CvVersion,
)

REPLIED_OR_BEYOND = frozenset(
    {ApplicationStatus.REPLIED, ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER}
)
INTERVIEW_OR_BEYOND = frozenset({ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER})


@dataclass(frozen=True, slots=True)
class FunnelRow:
    """Одна версія CV; `cv` None — «невідомо» (подачі без CV і старі подачі)."""

    cv: CvVersion | None
    applications: int
    replies: int
    interviews: int


def cv_funnel(applications: Iterable[Application]) -> tuple[FunnelRow, ...]:
    """Рядки за зростанням номера версії, «невідомо» останнім; без подач — порожньо."""
    groups: dict[int | None, list[Application]] = {}
    for application in applications:
        key = None if application.cv is None else application.cv.number
        groups.setdefault(key, []).append(application)
    known = sorted(key for key in groups if key is not None)
    order = [*known, None] if None in groups else known
    return tuple(_row(groups[key]) for key in order)


def _row(group: list[Application]) -> FunnelRow:
    return FunnelRow(
        cv=group[0].cv,
        applications=len(group),
        replies=sum(item.status in REPLIED_OR_BEYOND for item in group),
        interviews=sum(item.status in INTERVIEW_OR_BEYOND for item in group),
    )
