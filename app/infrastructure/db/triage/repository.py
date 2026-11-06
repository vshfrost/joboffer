"""TriageRepository на Postgres.

Кандидат — не схована вакансія користувача з текстом без аналізу й відмови (подача rejected /
withdrawn); агентові — ще й без тріажу або з тріажем `rules` і вердиктом maybe. Тріаж агента (`save`, `source = agent`) перезаписує рядок (`ON CONFLICT (job_id)`), перший
`id` лишається. Тріаж за правилами (`save_auto`, `source = rules`) — з відбитком вхідних даних; його
cron перераховує, коли відбиток змінився, а рядок `agent` не торкає ніколи.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, Text, cast, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.applications.application import CLOSED_STATUSES
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import Job
from domain.triage import scoring
from domain.triage.ids import TriageId
from domain.triage.scoring import CONTEXT_SEPARATOR, FIELD_SEPARATOR
from domain.triage.triage import TriageEntry, TriageSource, TriageVerdict
from infrastructure.db.analysis.tables import AnalysisRow
from infrastructure.db.applications.tables import ApplicationRow
from infrastructure.db.jobs.tables import JobRow
from infrastructure.db.triage.tables import TriageRow

# Ключ pg advisory lock прогону тріажу за правилами: один прогін на базу.
RUN_LOCK_KEY = 0x7472696167653031  # «triage01» в ASCII


class PostgresTriage:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def candidates(self, user_id: UserId, limit: int) -> list[Job]:
        return await self._jobs(_untriaged(user_id), limit)

    async def pending(self, user_id: UserId) -> int:
        count = await self._session.scalar(
            select(func.count()).select_from(JobRow).where(*_untriaged(user_id))
        )
        return int(count or 0)

    async def save(
        self,
        user_id: UserId,
        items: Sequence[tuple[TriageId, JobId, TriageEntry]],
        now: datetime,
    ) -> None:
        for triage_id, job_id, entry in items:
            values = {
                "score": entry.score,
                "verdict": entry.verdict.value,
                "reason": entry.reason,
                "triaged_at": now,
                "source": TriageSource.AGENT.value,
                "inputs_hash": None,
            }
            await self._session.execute(
                pg_insert(TriageRow)
                .values(
                    id=triage_id.value,
                    user_id=user_id.value,
                    job_id=job_id.value,
                    **values,
                )
                .on_conflict_do_update(index_elements=[TriageRow.job_id], set_=values)
            )

    async def lock(self) -> bool:
        # Транзакційне: відпускається з commit / rollback, навіть якщо процес упав.
        locked: bool = (
            await self._session.execute(
                select(func.pg_try_advisory_xact_lock(RUN_LOCK_KEY))
            )
        ).scalar_one()
        return locked

    async def users_with_work(self) -> list[UserId]:
        rows = await self._session.scalars(
            select(JobRow.user_id)
            .where(
                *_wanted(),
                ~exists().where(
                    TriageRow.job_id == JobRow.id,
                    TriageRow.source == TriageSource.AGENT.value,
                ),
            )
            .distinct()
            .order_by(JobRow.user_id)
        )
        return [UserId(row) for row in rows]

    async def users_with_jobs(self) -> list[UserId]:
        rows = await self._session.scalars(
            select(JobRow.user_id)
            .where(JobRow.text.is_not(None))
            .distinct()
            .order_by(JobRow.user_id)
        )
        return [UserId(row) for row in rows]

    async def auto_candidates(
        self, user_id: UserId, context: str, limit: int
    ) -> list[Job]:
        current = _inputs_hash(context)
        return await self._jobs(
            (
                JobRow.user_id == user_id.value,
                *_wanted(),
                # Не кандидат лише тріаж агента й тріаж правил із поточним відбитком.
                ~exists().where(
                    TriageRow.job_id == JobRow.id,
                    or_(
                        TriageRow.source == TriageSource.AGENT.value,
                        TriageRow.inputs_hash == current,
                    ),
                ),
            ),
            limit,
        )

    async def save_auto(
        self,
        user_id: UserId,
        items: Sequence[tuple[TriageId, JobId, TriageEntry, str]],
        now: datetime,
    ) -> None:
        for triage_id, job_id, entry, digest in items:
            values = {
                "score": entry.score,
                "verdict": entry.verdict.value,
                "reason": entry.reason,
                "triaged_at": now,
                "source": TriageSource.RULES.value,
                "inputs_hash": digest,
            }
            await self._session.execute(
                pg_insert(TriageRow)
                .values(
                    id=triage_id.value,
                    user_id=user_id.value,
                    job_id=job_id.value,
                    **values,
                )
                .on_conflict_do_update(
                    index_elements=[TriageRow.job_id],
                    set_=values,
                    # Рядок агента лишається як є: конфлікт з ним нічого не міняє.
                    where=TriageRow.source == TriageSource.RULES.value,
                )
            )

    async def analysed_scores(self, user_id: UserId) -> list[tuple[Job, int]]:
        rows = await self._session.execute(
            select(JobRow, AnalysisRow.score)
            .join(AnalysisRow, AnalysisRow.job_id == JobRow.id)
            .where(JobRow.user_id == user_id.value, JobRow.text.is_not(None))
            .order_by(JobRow.job_number)
            .execution_options(populate_existing=True)
        )
        return [(_job(row), score) for row, score in rows]

    async def _jobs(
        self, conditions: tuple[ColumnElement[bool], ...], limit: int
    ) -> list[Job]:
        rows = await self._session.scalars(
            select(JobRow)
            .where(*conditions)
            .order_by(JobRow.created_at.desc(), JobRow.job_number.desc())
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        return [_job(row) for row in rows]


def _job(row: JobRow) -> Job:
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
    )


def _inputs_hash(context: str) -> ColumnElement[str]:
    """`domain.triage.scoring.inputs_hash` у SQL: sha256 від версії правил, контексту й полів вакансії."""
    fields = func.concat_ws(
        cast(literal(FIELD_SEPARATOR), Text),
        JobRow.title,
        JobRow.location,
        JobRow.text,
    )
    prefix = f"{scoring.RULES_VERSION}{CONTEXT_SEPARATOR}{context}{CONTEXT_SEPARATOR}"
    joined = func.concat(cast(literal(prefix), Text), fields)
    return func.encode(func.sha256(func.convert_to(joined, "UTF8")), "hex")


def _wanted() -> tuple[ColumnElement[bool], ...]:
    """Не схована вакансія з текстом без повного аналізу й закритої подачі (правило кандидата)."""
    return (
        JobRow.dismissed_at.is_(None),
        JobRow.text.is_not(None),
        ~exists().where(AnalysisRow.job_id == JobRow.id),
        ~exists().where(
            ApplicationRow.job_id == JobRow.id,
            ApplicationRow.status.in_([status.value for status in CLOSED_STATUSES]),
        ),
    )


def _untriaged(user_id: UserId) -> tuple[ColumnElement[bool], ...]:
    """Своя вакансія за правилом кандидата, яку агент ще не бачив: без тріажу або з тріажем `rules` і
    вердиктом maybe. Решту (`rules` analyse / skip, будь-який `agent`) агент не бере."""
    return (
        JobRow.user_id == user_id.value,
        *_wanted(),
        ~exists().where(
            TriageRow.job_id == JobRow.id,
            or_(
                TriageRow.source != TriageSource.RULES.value,
                TriageRow.verdict != TriageVerdict.MAYBE.value,
            ),
        ),
    )
