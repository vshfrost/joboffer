"""Дошка відповідей у вебі: три черги, пошук, сторінки, ефект розбору на подачу."""

from dataclasses import dataclass
from enum import StrEnum

from domain.applications.application import ApplicationStatus
from domain.mail.inbox import FIRST_MAIL_PAGE, MailPage, MailQuery
from domain.mail.replies import Reply, ReplyType, review_target
from domain.shared.errors import InvalidFields
from domain.shared.problems import Problems


class ReplyQueue(StrEnum):
    """«До розбору» — нерозібрані зі збігом, «Без вакансії» — нерозібрані без збігу, «Розібрані»."""

    MATCHED = "matched"
    UNMATCHED = "unmatched"
    REVIEWED = "reviewed"


@dataclass(frozen=True, slots=True)
class ReplyQuery:
    """Що показати: черга, підрядок пошуку, сторінка."""

    queue: ReplyQueue = ReplyQueue.MATCHED
    text: str = ""
    page: MailPage = FIRST_MAIL_PAGE

    @classmethod
    def parse(
        cls,
        *,
        queue: str = "matched",
        text: str = "",
        page: int = 1,
        per_page: int = 20,
    ) -> ReplyQuery:
        """`InvalidFields` — усі помилки полів разом (queue, q, page, per_page); межі пошуку й
        сторінок — ті самі, що у «Вхідних»."""
        problems = Problems()
        try:
            found = ReplyQueue(queue.strip())
        except ValueError:
            allowed = ", ".join(item.value for item in ReplyQueue)
            problems.add("queue", f"Черга — одна з: {allowed}.")
            found = ReplyQueue.MATCHED
        try:
            mail = MailQuery.parse(text=text, page=page, per_page=per_page)
        except InvalidFields as error:
            for problem in error.problems:
                problems.add(problem.field, problem.message)
            mail = MailQuery()
        problems.raise_if_any()
        return cls(found, mail.text, mail.page)


@dataclass(frozen=True, slots=True)
class ReplyCounts:
    """Скільки відповідей у кожній черзі (пошук не враховується)."""

    matched: int = 0
    unmatched: int = 0
    reviewed: int = 0


@dataclass(frozen=True, slots=True)
class ReplyBoard:
    items: tuple[Reply, ...]
    page: MailPage
    counts: ReplyCounts


@dataclass(frozen=True, slots=True)
class ReviewEffect:
    """Що розбір зробить з подачею: статус зараз і після; `None` — розбір без вакансії."""

    job_number: int | None
    current: ApplicationStatus | None
    after: ApplicationStatus | None

    @property
    def changes(self) -> bool:
        return self.current != self.after


def review_effect(
    kind: ReplyType, job_number: int | None, current: ApplicationStatus | None
) -> ReviewEffect:
    """Ефект розбору типом `kind` на подачу вакансії `job_number` зі статусом `current`: ті самі
    правила, що в самому розборі (`review_target`)."""
    if job_number is None or current is None:
        return ReviewEffect(None, None, None)
    return ReviewEffect(job_number, current, review_target(kind, current) or current)
