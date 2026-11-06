"""Команди й результати розбору відповідей: примітиви й незмінні значення домену."""

from dataclasses import dataclass

from application.contracts.applications import ApplicationData
from domain.mail.replies import AppliedJob, Reply


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewInput:
    """Розбір відповіді з будь-якого транспорту; тип розбирає домен."""

    reply_id: int
    type: str
    # None — лист не про жодну подачу.
    job_number: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewedReplyData:
    reply: Reply
    # Подача після розбору; None — лист не про подачу.
    application: ApplicationData | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplyDetailData:
    """Відповідь для читалки: `reply.text` уже підготовлений для людини; подачі власника — з яких
    обирається вакансія."""

    reply: Reply
    applications: tuple[AppliedJob, ...]
