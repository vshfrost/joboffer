"""JobReplyRepository на Postgres (AsyncSession одного UoW): зіставлення листів компаній з
подачами користувача й розбір відповідей.

Вакансія скрізь — за номером у межах користувача; у таблиці вона лежить як UUID, тож номер
зводиться до нього через `jobs` з фільтром за користувачем (чужа й неіснуюча не відрізняються).
Один лист — одна відповідь: повторне зіставлення того самого листа нічого не дублює.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.applications.application import ApplicationStatus, AtsPlatform
from domain.identity.ids import UserId
from domain.mail.board import ReplyCounts, ReplyQuery, ReplyQueue
from domain.mail.inbox import MailSummary
from domain.mail.mail import MailCategory
from domain.mail.replies import (
    AppliedJob,
    Confidence,
    MatchedBy,
    Reply,
    ReplyJob,
    ReplyMail,
    ReplyMatch,
    ReplyType,
)
from domain.mail.sender_auth import SenderAuth
from infrastructure.db.applications.tables import ApplicationRow
from infrastructure.db.jobs.tables import JobRow
from infrastructure.db.mail.repository import matches
from infrastructure.db.mail.tables import JobReplyRow, MailMessageRow


class PostgresJobReplies:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def pending(self) -> list[tuple[UserId, ReplyMail]]:
        found = await self._session.scalars(
            select(MailMessageRow)
            .outerjoin(JobReplyRow, JobReplyRow.mail_id == MailMessageRow.id)
            .where(
                MailMessageRow.category == MailCategory.COMPANY.value,
                JobReplyRow.id.is_(None),
            )
            .order_by(MailMessageRow.received_at, MailMessageRow.id)
        )
        return [
            (
                UserId(row.user_id),
                ReplyMail(
                    id=row.id,
                    received_at=row.received_at,
                    message_id=row.message_id,
                    in_reply_to=row.in_reply_to,
                    references=tuple(row.reference_ids),
                    from_address=row.from_address,
                    from_name=row.from_name,
                    subject=row.subject,
                    text=row.untrusted_text,
                    sender_auth=SenderAuth(row.sender_auth),
                ),
            )
            for row in found
        ]

    async def thread_job(
        self, user_id: UserId, message_ids: Sequence[str]
    ) -> int | None:
        if not message_ids:
            return None
        return await self._session.scalar(
            select(JobRow.job_number)
            .join(JobReplyRow, JobReplyRow.job_id == JobRow.id)
            .join(MailMessageRow, MailMessageRow.id == JobReplyRow.mail_id)
            .where(
                JobReplyRow.user_id == user_id.value,
                MailMessageRow.message_id.in_(message_ids),
            )
            .order_by(JobReplyRow.id.desc())
            .limit(1)
        )

    async def add(
        self, user_id: UserId, mail_id: int, match: ReplyMatch, suggested: ReplyType
    ) -> None:
        await self._session.execute(
            pg_insert(JobReplyRow)
            .values(
                user_id=user_id.value,
                mail_id=mail_id,
                job_id=await self._job_id(user_id, match.job_number),
                confidence=None if match.confidence is None else match.confidence.value,
                matched_by=None if match.matched_by is None else match.matched_by.value,
                suggested_type=suggested.value,
            )
            .on_conflict_do_nothing(index_elements=[JobReplyRow.mail_id])
        )

    async def applied(self, user_id: UserId) -> list[AppliedJob]:
        found = await self._session.execute(
            select(ApplicationRow, JobRow.job_number, JobRow.title, JobRow.company)
            .join(JobRow, JobRow.id == ApplicationRow.job_id)
            .where(ApplicationRow.user_id == user_id.value)
            .order_by(ApplicationRow.applied_on.desc(), JobRow.job_number.desc())
        )
        return [
            AppliedJob(
                job_number=number,
                title=title,
                company=company,
                status=ApplicationStatus(row.status),
                ats=None if row.ats is None else AtsPlatform(row.ats),
                company_domains=tuple(row.company_domains),
                company_emails=tuple(row.company_emails),
            )
            for row, number, title, company in found
        ]

    async def list(self, user_id: UserId, *, reviewed: bool, limit: int) -> list[Reply]:
        done = JobReplyRow.reviewed_at.is_not(None)
        found = await self._session.execute(
            _replies(user_id)
            .where(done if reviewed else ~done)
            .order_by(MailMessageRow.received_at.desc(), JobReplyRow.id.desc())
            .limit(limit)
        )
        return [_reply(*row) for row in found]

    async def search(
        self, user_id: UserId, query: ReplyQuery
    ) -> tuple[Sequence[Reply], int]:
        found = _replies(user_id).where(
            _in_queue(query.queue),
            *matches(
                query.text,
                JobRow.company,
                MailMessageRow.from_name,
                MailMessageRow.from_address,
                MailMessageRow.subject,
                MailMessageRow.untrusted_text,
            ),
        )
        total = (
            await self._session.execute(found.with_only_columns(func.count()))
        ).scalar_one()
        page = query.page
        rows = await self._session.execute(
            found.order_by(MailMessageRow.received_at.desc(), JobReplyRow.id.desc())
            .limit(page.size)
            .offset(page.offset)
        )
        return [_reply(*row) for row in rows], total

    async def counts(self, user_id: UserId) -> ReplyCounts:
        matched, unmatched, reviewed = (
            await self._session.execute(
                select(
                    func.count().filter(_in_queue(ReplyQueue.MATCHED)),
                    func.count().filter(_in_queue(ReplyQueue.UNMATCHED)),
                    func.count().filter(_in_queue(ReplyQueue.REVIEWED)),
                ).where(JobReplyRow.user_id == user_id.value)
            )
        ).one()
        return ReplyCounts(matched, unmatched, reviewed)

    async def get(self, user_id: UserId, reply_id: int) -> Reply | None:
        row = (
            await self._session.execute(
                _replies(user_id).where(JobReplyRow.id == reply_id)
            )
        ).one_or_none()
        return None if row is None else _reply(*row)

    async def review(
        self,
        user_id: UserId,
        reply_id: int,
        job_number: int | None,
        reply_type: ReplyType,
        reviewed_at: datetime,
    ) -> Reply:
        await self._session.execute(
            update(JobReplyRow)
            .where(JobReplyRow.id == reply_id, JobReplyRow.user_id == user_id.value)
            .values(
                job_id=await self._job_id(user_id, job_number),
                type=reply_type.value,
                reviewed_at=reviewed_at,
            )
        )
        row = (
            await self._session.execute(
                _replies(user_id)
                .where(JobReplyRow.id == reply_id)
                .execution_options(populate_existing=True)
            )
        ).one()
        return _reply(*row)

    async def _job_id(self, user_id: UserId, job_number: int | None) -> UUID | None:
        if job_number is None:
            return None
        return await self._session.scalar(
            select(JobRow.id).where(
                JobRow.user_id == user_id.value, JobRow.job_number == job_number
            )
        )


def _in_queue(queue: ReplyQueue) -> ColumnElement[bool]:
    """Нерозібрані зі збігом, нерозібрані без збігу, розібрані."""
    done = JobReplyRow.reviewed_at.is_not(None)
    if queue is ReplyQueue.REVIEWED:
        return done
    matched = JobReplyRow.job_id.is_not(None)
    return and_(~done, matched if queue is ReplyQueue.MATCHED else ~matched)


def _replies(user_id: UserId) -> Select[*tuple[Any, ...]]:
    """Відповіді користувача з листом, вакансією й статусом подачі (вакансії й подачі може не бути)."""
    return (
        select(JobReplyRow, MailMessageRow, JobRow, ApplicationRow.status)
        .join(MailMessageRow, MailMessageRow.id == JobReplyRow.mail_id)
        .outerjoin(JobRow, JobRow.id == JobReplyRow.job_id)
        .outerjoin(ApplicationRow, ApplicationRow.job_id == JobReplyRow.job_id)
        .where(JobReplyRow.user_id == user_id.value)
    )


def _reply(
    reply: JobReplyRow, mail: MailMessageRow, job: JobRow | None, status: Any
) -> Reply:
    return Reply(
        id=reply.id,
        mail=MailSummary(
            id=mail.id,
            from_address=mail.from_address,
            from_name=mail.from_name,
            subject=mail.subject,
            category=MailCategory(mail.category),
            received_at=mail.received_at,
            sender_auth=SenderAuth(mail.sender_auth),
        ),
        text=mail.untrusted_text,
        job=None
        if job is None
        else ReplyJob(
            job.job_number,
            job.title,
            job.company,
            None if status is None else ApplicationStatus(status),
        ),
        confidence=None if reply.confidence is None else Confidence(reply.confidence),
        matched_by=None if reply.matched_by is None else MatchedBy(reply.matched_by),
        suggested_type=ReplyType(reply.suggested_type),
        type=None if reply.type is None else ReplyType(reply.type),
        reviewed_at=reply.reviewed_at,
    )
