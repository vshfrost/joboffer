"""ApplicationRepository на Postgres.

Подача належить вакансії користувача; номер вакансії зводиться до її UUID через `jobs` з
фільтром за користувачем, тож чужа й неіснуюча не відрізняються. Повторне збереження міняє
лише деталі: статус і час його зміни лишаються. Версія CV лежить в окремій таблиці: нема рядка —
«невідома».
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.applications.application import (
    Application,
    ApplicationChannel,
    ApplicationStatus,
    AtsPlatform,
    CvVersion,
    NewApplication,
)
from domain.identity.ids import UserId
from domain.jobs.job import MAX_JOB_NUMBER
from infrastructure.db.applications.tables import (
    ApplicationCvVersionRow,
    ApplicationRow,
)
from infrastructure.db.jobs.tables import JobRow


class PostgresApplications:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UserId, job_number: int) -> Application | None:
        if not 1 <= job_number <= MAX_JOB_NUMBER:
            return None
        row = (
            await self._session.execute(
                select(ApplicationRow, JobRow.job_number, ApplicationCvVersionRow)
                .join(JobRow, JobRow.id == ApplicationRow.job_id)
                .outerjoin(
                    ApplicationCvVersionRow,
                    ApplicationCvVersionRow.job_id == ApplicationRow.job_id,
                )
                .where(JobRow.user_id == user_id.value, JobRow.job_number == job_number)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        return None if row is None else _application(row[0], row[1], _cv(row[2]))

    async def save(
        self, user_id: UserId, job_number: int, details: NewApplication, now: datetime
    ) -> Application:
        job_id = await self._job_id(user_id, job_number)
        values = {
            "applied_on": details.applied_on,
            "channel": details.channel.value,
            "ats": None if details.ats is None else details.ats.value,
            "company_domains": list(details.company_domains),
            "company_emails": list(details.company_emails),
        }
        saved = await self._session.execute(
            pg_insert(ApplicationRow)
            .values(
                job_id=job_id,
                user_id=user_id.value,
                status=ApplicationStatus.APPLIED.value,
                status_changed_at=now,
                created_at=now,
                updated_at=now,
                **values,
            )
            .on_conflict_do_update(
                index_elements=[ApplicationRow.job_id],
                set_={**values, "updated_at": now},
            )
            .returning(ApplicationRow)
            .execution_options(populate_existing=True)
        )
        row = saved.scalar_one()
        await self._save_cv(job_id, details.cv)
        return _application(row, job_number, details.cv)

    async def _save_cv(self, job_id: UUID, cv: CvVersion | None) -> None:
        """Версія подачі: нова замінює стару, `None` її забуває."""
        if cv is None:
            await self._session.execute(
                delete(ApplicationCvVersionRow).where(
                    ApplicationCvVersionRow.job_id == job_id
                )
            )
            return
        values = {
            "cv_number": cv.number,
            "saved_on": cv.saved_on,
            "coverage_percent": cv.coverage_percent,
        }
        await self._session.execute(
            pg_insert(ApplicationCvVersionRow)
            .values(job_id=job_id, **values)
            .on_conflict_do_update(
                index_elements=[ApplicationCvVersionRow.job_id], set_=values
            )
        )

    async def list_all(self, user_id: UserId) -> list[Application]:
        found = await self._session.execute(
            select(ApplicationRow, JobRow.job_number, ApplicationCvVersionRow)
            .join(JobRow, JobRow.id == ApplicationRow.job_id)
            .outerjoin(
                ApplicationCvVersionRow,
                ApplicationCvVersionRow.job_id == ApplicationRow.job_id,
            )
            .where(ApplicationRow.user_id == user_id.value)
            .order_by(JobRow.job_number)
            .execution_options(populate_existing=True)
        )
        return [_application(row, number, _cv(cv)) for row, number, cv in found]

    async def set_status(
        self,
        user_id: UserId,
        job_number: int,
        status: ApplicationStatus,
        now: datetime,
    ) -> Application:
        job_id = await self._job_id(user_id, job_number)
        changed = await self._session.execute(
            update(ApplicationRow)
            .where(ApplicationRow.job_id == job_id)
            .values(status=status.value, status_changed_at=now, updated_at=now)
            .returning(ApplicationRow)
            .execution_options(populate_existing=True)
        )
        row = changed.scalar_one_or_none()
        if row is None:
            raise LookupError(f"Подачі на вакансію {job_number} нема.")
        cv = await self._session.get(
            ApplicationCvVersionRow, job_id, populate_existing=True
        )
        return _application(row, job_number, _cv(cv))

    async def _job_id(self, user_id: UserId, job_number: int) -> UUID:
        job_id = await self._session.scalar(
            select(JobRow.id).where(
                JobRow.user_id == user_id.value, JobRow.job_number == job_number
            )
        )
        if job_id is None:
            raise LookupError(f"Вакансії {job_number} нема.")
        return job_id


def _cv(row: ApplicationCvVersionRow | None) -> CvVersion | None:
    return (
        None
        if row is None
        else CvVersion(
            number=row.cv_number,
            saved_on=row.saved_on,
            coverage_percent=row.coverage_percent,
        )
    )


def _application(
    row: ApplicationRow, job_number: int, cv: CvVersion | None
) -> Application:
    return Application(
        job_number=job_number,
        status=ApplicationStatus(row.status),
        applied_on=row.applied_on,
        channel=ApplicationChannel(row.channel),
        ats=None if row.ats is None else AtsPlatform(row.ats),
        company_domains=tuple(row.company_domains),
        company_emails=tuple(row.company_emails),
        status_changed_at=row.status_changed_at,
        cv=cv,
    )
