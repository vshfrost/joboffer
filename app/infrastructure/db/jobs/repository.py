"""JobRepository на Postgres.

Номер вакансії видає `job_counters`: апсерт рядка користувача блокує його до кінця транзакції,
тож паралельні додавання одного користувача йдуть по черзі, а скасована транзакція номер не
витрачає. Явний номер (перенос з v1) лічильник не відсуває назад.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import (
    ColumnElement,
    and_,
    case,
    exists,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.applications.application import (
    ACTIVE_STATUSES,
    ApplicationStatus,
)
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import (
    MAX_JOB_NUMBER,
    NEW_BADGE_SOURCE_PREFIXES,
    Job,
    JobSummary,
    NewJob,
)
from domain.jobs.linkedin import linkedin_job_url
from domain.jobs.search import JobSearch, JobStage, JobTabCounts
from domain.profile.modes import WorkMode
from domain.shared.fingerprint import text_fingerprint
from domain.sources.dedup import RecentJob
from domain.triage.triage import Triage, TriageSource, TriageVerdict
from infrastructure.db.analysis.tables import AnalysisRow
from infrastructure.db.applications.tables import ApplicationRow
from infrastructure.db.documents.tables import DocumentRow
from infrastructure.db.facts.tables import FactRow
from infrastructure.db.jobs.tables import JobCounterRow, JobRow
from infrastructure.db.mail.tables import JobReplyRow
from infrastructure.db.prep.tables import InterviewKitRow, PrepTopicJobRow
from infrastructure.db.triage.tables import TriageRow

LIKE_ESCAPE = "\\"
ACTIVE = [status.value for status in ACTIVE_STATUSES]


class PostgresJobs:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_additions(self, user_id: UserId) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:user, 0))"),
            {"user": f"jobs:{user_id}"},
        )

    async def find_duplicate(self, user_id: UserId, job: NewJob) -> int | None:
        # NULL нічого не дублює: порівнюємо лише те, що в вакансії є.
        same = []
        if job.fingerprint is not None:
            same.append(JobRow.text_hash == job.fingerprint)
        if job.url is not None:
            same.append(JobRow.url == job.url)
        if job.linkedin_id is not None:
            same.append(JobRow.linkedin_id == job.linkedin_id)
        if not same:
            return None
        return await self._session.scalar(
            select(JobRow.job_number)
            .where(JobRow.user_id == user_id.value, or_(*same))
            .order_by(JobRow.job_number)
            .limit(1)
        )

    async def find_linkedin(self, user_id: UserId, linkedin_id: str) -> int | None:
        return await self._session.scalar(
            select(JobRow.job_number)
            .where(
                JobRow.user_id == user_id.value,
                or_(
                    JobRow.linkedin_id == linkedin_id,
                    JobRow.url == linkedin_job_url(linkedin_id),
                ),
            )
            .order_by(JobRow.job_number)
            .limit(1)
        )

    async def add(
        self,
        user_id: UserId,
        job_id: JobId,
        job: NewJob,
        now: datetime,
        number: int | None = None,
    ) -> int:
        given = await self._reserve_number(user_id, number)
        self._session.add(
            JobRow(
                id=job_id.value,
                user_id=user_id.value,
                job_number=given,
                source=job.source,
                url=job.url,
                title=job.title,
                company=job.company,
                text=job.text,
                text_hash=job.fingerprint,
                linkedin_id=job.linkedin_id,
                location=job.location,
                created_at=now,
            )
        )
        await self._session.flush()
        return given

    async def _reserve_number(self, user_id: UserId, explicit: int | None) -> int:
        if explicit is None:
            counter = pg_insert(JobCounterRow).values(
                user_id=user_id.value, last_number=1
            )
            update_to = JobCounterRow.last_number + 1
        else:
            counter = pg_insert(JobCounterRow).values(
                user_id=user_id.value, last_number=max(explicit, 0)
            )
            update_to = func.greatest(JobCounterRow.last_number, explicit)
        reserved = await self._session.scalar(
            counter.on_conflict_do_update(
                index_elements=[JobCounterRow.user_id], set_={"last_number": update_to}
            ).returning(JobCounterRow.last_number)
        )
        return explicit if explicit is not None else int(reserved or 0)

    async def recent(self, user_id: UserId, since: datetime) -> list[RecentJob]:
        rows = await self._session.execute(
            select(
                JobRow.job_number,
                JobRow.company,
                JobRow.title,
                JobRow.text.is_(None).label("needs_text"),
            )
            .where(JobRow.user_id == user_id.value, JobRow.created_at >= since)
            .order_by(JobRow.job_number)
        )
        return [
            RecentJob(row.job_number, row.company, row.title, row.needs_text)
            for row in rows
        ]

    async def complete_text(self, user_id: UserId, number: int, text: str) -> None:
        await self._session.execute(
            update(JobRow)
            .where(
                JobRow.user_id == user_id.value,
                JobRow.job_number == number,
                JobRow.text.is_(None),
            )
            .values(text=text, text_hash=text_fingerprint(text))
        )

    async def get(self, user_id: UserId, number: int) -> Job | None:
        if not 1 <= number <= MAX_JOB_NUMBER:
            return None
        row = await self._session.scalar(
            select(JobRow)
            .where(JobRow.user_id == user_id.value, JobRow.job_number == number)
            .execution_options(populate_existing=True)
        )
        if row is None:
            return None
        return _job_of(row)

    async def mark_opened(self, user_id: UserId, number: int, now: datetime) -> None:
        await self._session.execute(
            update(JobRow)
            .where(
                JobRow.user_id == user_id.value,
                JobRow.job_number == number,
                JobRow.opened_at.is_(None),
            )
            .values(opened_at=now)
        )

    async def search(self, user_id: UserId, search: JobSearch) -> list[JobSummary]:
        statement = (
            select(
                JobRow.job_number,
                JobRow.source,
                JobRow.url,
                JobRow.title,
                JobRow.company,
                JobRow.created_at,
                JobRow.text.is_(None).label("needs_text"),
                JobRow.dismissed_at.is_not(None).label("dismissed"),
                AnalysisRow.score.label("score"),
                AnalysisRow.filters_passed.label("filters_passed"),
                AnalysisRow.work_mode.label("work_mode"),
                TriageRow.score.label("triage_score"),
                TriageRow.verdict.label("triage_verdict"),
                TriageRow.reason.label("triage_reason"),
                ApplicationRow.status.label("status"),
                and_(
                    JobRow.opened_at.is_(None),
                    or_(
                        *(
                            JobRow.source.startswith(prefix)
                            for prefix in NEW_BADGE_SOURCE_PREFIXES
                        )
                    ),
                ).label("is_new"),
            )
            .select_from(JobRow)
            .outerjoin(AnalysisRow, AnalysisRow.job_id == JobRow.id)
            .outerjoin(TriageRow, TriageRow.job_id == JobRow.id)
            .outerjoin(ApplicationRow, ApplicationRow.job_id == JobRow.id)
            .where(
                JobRow.user_id == user_id.value,
                JobRow.dismissed_at.is_not(None)
                if search.dismissed
                else JobRow.dismissed_at.is_(None),
            )
        )
        if search.query is not None:
            pattern = f"%{_escape_like(search.query)}%"
            statement = statement.where(
                or_(
                    *(
                        column.ilike(pattern, escape=LIKE_ESCAPE)
                        for column in (JobRow.title, JobRow.company, JobRow.text)
                    )
                )
            )
        if search.since is not None:
            statement = statement.where(JobRow.created_at >= search.since)
        if search.source is not None:
            statement = statement.where(JobRow.source == search.source)
        if search.needs_text:
            statement = statement.where(JobRow.text.is_(None))
        if search.work_mode is not None:
            statement = statement.where(AnalysisRow.work_mode == search.work_mode.value)
        if search.triage_verdict is not None:
            statement = statement.where(
                TriageRow.verdict == search.triage_verdict.value
            )
        if search.statuses is not None:
            statement = statement.where(
                ApplicationRow.status.in_([s.value for s in search.statuses])
            )
        if search.stage is not None:
            statement = statement.where(_in_stage(search.stage))
        if search.hide_rejected:
            statement = statement.where(_not_rejected())
        rows = await self._session.execute(
            statement.order_by(
                # Без тексту — наприкінці; проаналізовані першими, серед них — ті, що пройшли
                # фільтри, за скором; далі за тріажем (analyse → maybe → skip, без тріажу —
                # після нього) і його скором; далі новіші першими.
                JobRow.text.is_(None),
                AnalysisRow.job_id.is_(None),
                AnalysisRow.filters_passed.desc(),
                AnalysisRow.score.desc(),
                case(
                    (TriageRow.verdict == TriageVerdict.ANALYSE.value, 0),
                    (TriageRow.verdict == TriageVerdict.MAYBE.value, 1),
                    (TriageRow.verdict == TriageVerdict.SKIP.value, 2),
                    else_=3,
                ),
                TriageRow.score.desc().nulls_last(),
                JobRow.created_at.desc(),
                JobRow.job_number.desc(),
            ).limit(search.limit)
        )
        return [
            JobSummary(
                number=row.job_number,
                source=row.source,
                url=row.url,
                title=row.title,
                company=row.company,
                created_at=row.created_at,
                needs_text=row.needs_text,
                dismissed=row.dismissed,
                score=row.score,
                filters_passed=row.filters_passed,
                work_mode=None if row.work_mode is None else WorkMode(row.work_mode),
                triage_score=row.triage_score,
                triage_verdict=None
                if row.triage_verdict is None
                else TriageVerdict(row.triage_verdict),
                triage_reason=row.triage_reason,
                status=None if row.status is None else ApplicationStatus(row.status),
                is_new=row.is_new,
            )
            for row in rows
        ]

    async def tab_counts(self, user_id: UserId) -> JobTabCounts:
        mine = JobRow.user_id == user_id.value
        in_progress = await self._session.scalar(
            select(func.count())
            .select_from(JobRow)
            .outerjoin(ApplicationRow, ApplicationRow.job_id == JobRow.id)
            .where(mine, JobRow.dismissed_at.is_(None), _in_stage(JobStage.IN_PROGRESS))
        )
        unreviewed = await self._session.scalar(
            select(func.count(func.distinct(JobReplyRow.job_id))).where(
                JobReplyRow.user_id == user_id.value,
                JobReplyRow.reviewed_at.is_(None),
                JobReplyRow.job_id.is_not(None),
                ApplicationRow.job_id == JobReplyRow.job_id,
                ApplicationRow.status.in_(ACTIVE),
            )
        )
        needs_text = await self._session.scalar(
            select(
                exists()
                .where(mine, JobRow.dismissed_at.is_(None), JobRow.text.is_(None))
                .where(
                    ~exists().where(
                        ApplicationRow.job_id == JobRow.id,
                        ApplicationRow.status == ApplicationStatus.REJECTED.value,
                    )
                )
            )
        )
        return JobTabCounts(
            in_progress=in_progress or 0,
            applied_unreviewed=unreviewed or 0,
            needs_text=bool(needs_text),
        )

    async def get_triage(self, user_id: UserId, number: int) -> Triage | None:
        row = (
            await self._session.execute(
                select(TriageRow)
                .join(JobRow, JobRow.id == TriageRow.job_id)
                .where(JobRow.user_id == user_id.value, JobRow.job_number == number)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return Triage(
            job_number=number,
            score=row.score,
            verdict=TriageVerdict(row.verdict),
            reason=row.reason,
            triaged_at=row.triaged_at,
            source=TriageSource(row.source),
        )

    async def sources(self, user_id: UserId) -> list[str]:
        return list(
            await self._session.scalars(
                select(JobRow.source)
                .distinct()
                .where(JobRow.user_id == user_id.value)
                .order_by(JobRow.source)
            )
        )

    async def source_jobs(self, user_id: UserId) -> list[Job]:
        rows = await self._session.scalars(
            select(JobRow)
            .where(
                JobRow.user_id == user_id.value,
                JobRow.dismissed_at.is_(None),
                JobRow.text.is_not(None),
                or_(
                    *(
                        JobRow.source.startswith(prefix)
                        for prefix in NEW_BADGE_SOURCE_PREFIXES
                    )
                ),
                ~exists().where(AnalysisRow.job_id == JobRow.id).correlate(JobRow),
                ~exists().where(ApplicationRow.job_id == JobRow.id),
            )
            .order_by(JobRow.job_number)
        )
        return [_job_of(row) for row in rows]

    async def dismiss(
        self, user_id: UserId, numbers: Sequence[int], reason: str, now: datetime
    ) -> None:
        await self._session.execute(
            update(JobRow)
            .where(
                JobRow.user_id == user_id.value,
                JobRow.job_number.in_(numbers),
                JobRow.dismissed_at.is_(None),
            )
            .values(dismissed_at=now, dismiss_reason=reason)
        )

    async def restore(self, user_id: UserId, number: int) -> None:
        await self._session.execute(
            update(JobRow)
            .where(JobRow.user_id == user_id.value, JobRow.job_number == number)
            .values(dismissed_at=None, dismiss_reason=None)
        )


def _has_interaction() -> ColumnElement[bool]:
    """Користувач щось робив із вакансією: аналіз, документ (CV чи лист), interview kit, тема
    підготовки чи факт вакансії. Тріаж і відкриття деталей — не взаємодія."""
    return or_(
        exists().where(AnalysisRow.job_id == JobRow.id).correlate(JobRow),
        exists().where(DocumentRow.job_id == JobRow.id).correlate(JobRow),
        exists().where(InterviewKitRow.job_id == JobRow.id).correlate(JobRow),
        exists().where(PrepTopicJobRow.job_id == JobRow.id).correlate(JobRow),
        exists().where(FactRow.job_uuid == JobRow.id).correlate(JobRow),
    )


def _not_rejected() -> ColumnElement[bool]:
    """Потрібен `ApplicationRow` у FROM (outer join)."""
    return or_(
        ApplicationRow.job_id.is_(None),
        ApplicationRow.status != ApplicationStatus.REJECTED.value,
    )


def _in_stage(stage: JobStage) -> ColumnElement[bool]:
    """Етап для табів вебу; потрібен `ApplicationRow` у FROM (outer join). Не врахована схованість."""
    if stage is JobStage.APPLIED:
        return ApplicationRow.status.in_(ACTIVE)
    if stage is JobStage.IN_PROGRESS:
        return or_(
            ApplicationRow.status == ApplicationStatus.WITHDRAWN.value,
            and_(ApplicationRow.job_id.is_(None), _has_interaction()),
        )
    return and_(
        JobRow.text.is_not(None),
        ApplicationRow.job_id.is_(None),
        ~_has_interaction(),
    )


def _job_of(row: JobRow) -> Job:
    return Job(
        id=JobId(row.id),
        number=row.job_number,
        source=row.source,
        text=row.text,
        url=row.url,
        title=row.title,
        company=row.company,
        created_at=row.created_at,
        location=row.location,
        dismissed_at=row.dismissed_at,
        dismiss_reason=row.dismiss_reason,
        opened_at=row.opened_at,
    )


def _escape_like(text: str) -> str:
    """Запит шукається буквально: %, _ і сам символ екранування не є шаблоном."""
    for char in (LIKE_ESCAPE, "%", "_"):
        text = text.replace(char, LIKE_ESCAPE + char)
    return text
