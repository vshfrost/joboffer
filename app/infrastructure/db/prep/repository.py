"""PrepTopicRepository на Postgres.

Номер теми видає `prep_topic_counters`: апсерт рядка користувача блокує його до кінця транзакції,
а скасована транзакція номер не витрачає. Збереження тем одного користувача йдуть по черзі
(advisory-замок): пошук теми за slug і вставка не б'ються з паралельним збереженням того самого
slug. Прив'язка — `ON CONFLICT (topic_id, job_id)`: повтор для вакансії замінює прогалину.
Скор вакансії береться з її аналізу в момент читання.

Кроки плану: номер кроку видає `prep_step_counters` (наскрізно по темах користувача, номери
видалених кроків не повторюються), заміна невиконаних кроків і нумерація йдуть під тим самим
advisory-замком користувача. Виконаний крок не видаляється й не змінюється заміною плану.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.prep.ids import StepId, TopicId
from domain.prep.plan import NewStep, PrepStep, Resource, StepKind
from domain.prep.topic import MAX_NUMBER, NewTopic, PrepTopic, TopicJob, TopicKind
from infrastructure.db.analysis.tables import AnalysisRow
from infrastructure.db.jobs.tables import JobRow
from infrastructure.db.prep.tables import (
    PrepStepCounterRow,
    PrepStepRow,
    PrepTopicCounterRow,
    PrepTopicJobRow,
    PrepTopicRow,
)


class PostgresPrepTopics:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(  # noqa: PLR0913, PLR0917
        self,
        user_id: UserId,
        topic_id: TopicId,
        job_id: JobId,
        topic: NewTopic,
        gap: str,
        now: datetime,
    ) -> int:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:user, 0))"),
            {"user": f"prep_topics:{user_id}"},
        )
        row = await self._session.scalar(
            select(PrepTopicRow)
            .where(
                PrepTopicRow.user_id == user_id.value, PrepTopicRow.slug == topic.slug
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            row = PrepTopicRow(
                id=topic_id.value,
                user_id=user_id.value,
                topic_number=await self._next_number(user_id),
                slug=topic.slug,
                created_at=now,
            )
            self._session.add(row)
        row.title = topic.title
        row.kind = topic.kind.value
        row.summary = topic.summary
        row.deadline = topic.deadline
        await self._session.flush()
        await self._session.execute(
            pg_insert(PrepTopicJobRow)
            .values(topic_id=row.id, job_id=job_id.value, gap=gap)
            .on_conflict_do_update(
                index_elements=[PrepTopicJobRow.topic_id, PrepTopicJobRow.job_id],
                set_={"gap": gap},
            )
        )
        return row.topic_number

    async def _next_number(self, user_id: UserId) -> int:
        reserved = await self._session.scalar(
            pg_insert(PrepTopicCounterRow)
            .values(user_id=user_id.value, last_number=1)
            .on_conflict_do_update(
                index_elements=[PrepTopicCounterRow.user_id],
                set_={"last_number": PrepTopicCounterRow.last_number + 1},
            )
            .returning(PrepTopicCounterRow.last_number)
        )
        return int(reserved or 0)

    async def all(self, user_id: UserId) -> list[PrepTopic]:
        return await self._topics(user_id, None)

    async def _topics(self, user_id: UserId, number: int | None) -> list[PrepTopic]:
        wanted = [PrepTopicRow.user_id == user_id.value]
        if number is not None:
            wanted.append(PrepTopicRow.topic_number == number)
        rows = await self._session.scalars(
            select(PrepTopicRow)
            .where(*wanted)
            .order_by(PrepTopicRow.topic_number)
            .execution_options(populate_existing=True)
        )
        links = await self._session.execute(
            select(
                PrepTopicJobRow.topic_id,
                JobRow.job_number,
                JobRow.title,
                JobRow.company,
                AnalysisRow.score,
                PrepTopicJobRow.gap,
            )
            .join(PrepTopicRow, PrepTopicRow.id == PrepTopicJobRow.topic_id)
            .join(JobRow, JobRow.id == PrepTopicJobRow.job_id)
            .join(AnalysisRow, AnalysisRow.job_id == JobRow.id)
            .where(*wanted)
            .order_by(JobRow.job_number)
        )
        jobs: dict[object, list[TopicJob]] = defaultdict(list)
        for topic_id, job_number, title, company, score, gap in links:
            jobs[topic_id].append(TopicJob(job_number, title, company, score, gap))
        step_rows = await self._session.scalars(
            select(PrepStepRow)
            .join(PrepTopicRow, PrepTopicRow.id == PrepStepRow.topic_id)
            .where(*wanted)
            .order_by(PrepStepRow.position)
            .execution_options(populate_existing=True)
        )
        steps: dict[object, list[PrepStep]] = defaultdict(list)
        for step in step_rows:
            steps[step.topic_id].append(_step(step))
        return [
            PrepTopic(
                id=TopicId(row.id),
                number=row.topic_number,
                slug=row.slug,
                title=row.title,
                kind=TopicKind(row.kind),
                summary=row.summary,
                deadline=row.deadline,
                created_at=row.created_at,
                jobs=tuple(jobs[row.id]),
                steps=tuple(steps[row.id]),
                ready_at=row.ready_at,
            )
            for row in rows
        ]

    async def get(self, user_id: UserId, number: int) -> PrepTopic | None:
        if not 1 <= number <= MAX_NUMBER:
            return None
        found = await self._topics(user_id, number)
        return found[0] if found else None

    async def replace_pending_steps(
        self,
        user_id: UserId,
        topic_number: int,
        steps: Sequence[tuple[StepId, NewStep]],
    ) -> None:
        await self._lock_steps(user_id)
        # Тему перевіряє use case: тут вона є.
        topic_id = (
            await self._session.execute(
                select(PrepTopicRow.id).where(
                    PrepTopicRow.user_id == user_id.value,
                    PrepTopicRow.topic_number == topic_number,
                )
            )
        ).scalar_one()
        await self._session.execute(
            delete(PrepStepRow).where(
                PrepStepRow.topic_id == topic_id, PrepStepRow.done_at.is_(None)
            )
        )
        position = await self._session.scalar(
            select(func.coalesce(func.max(PrepStepRow.position), 0)).where(
                PrepStepRow.topic_id == topic_id
            )
        )
        first = await self._reserve_step_numbers(user_id, len(steps))
        for offset, (step_id, step) in enumerate(steps):
            self._session.add(
                PrepStepRow(
                    id=step_id.value,
                    user_id=user_id.value,
                    topic_id=topic_id,
                    step_number=first + offset,
                    position=(position or 0) + offset + 1,
                    kind=step.kind.value,
                    title=step.title,
                    details=step.details,
                    resources=[
                        {"title": resource.title, "url": resource.url}
                        for resource in step.resources
                    ],
                    minutes=step.minutes,
                )
            )
        await self._session.flush()

    async def complete_step(
        self, user_id: UserId, step_number: int, note: str, now: datetime
    ) -> int | None:
        if not 1 <= step_number <= MAX_NUMBER:
            return None
        values: dict[str, object] = {"done_at": func.coalesce(PrepStepRow.done_at, now)}
        if note:
            values["note"] = note
        topic_id = await self._session.scalar(
            update(PrepStepRow)
            .where(
                PrepStepRow.user_id == user_id.value,
                PrepStepRow.step_number == step_number,
            )
            .values(**values)
            .returning(PrepStepRow.topic_id)
            .execution_options(synchronize_session=False)
        )
        if topic_id is None:
            return None
        return await self._session.scalar(
            select(PrepTopicRow.topic_number).where(PrepTopicRow.id == topic_id)
        )

    async def set_ready(
        self, user_id: UserId, topic_number: int, *, ready: bool, now: datetime
    ) -> None:
        await self._session.execute(
            update(PrepTopicRow)
            .where(
                PrepTopicRow.user_id == user_id.value,
                PrepTopicRow.topic_number == topic_number,
            )
            .values(
                ready_at=func.coalesce(PrepTopicRow.ready_at, now) if ready else None
            )
            .execution_options(synchronize_session=False)
        )

    async def _lock_steps(self, user_id: UserId) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:user, 0))"),
            {"user": f"prep_steps:{user_id}"},
        )

    async def _reserve_step_numbers(self, user_id: UserId, count: int) -> int:
        """Резервує `count` номерів поспіль і повертає перший."""
        if count == 0:
            return 0
        last = await self._session.scalar(
            pg_insert(PrepStepCounterRow)
            .values(user_id=user_id.value, last_number=count)
            .on_conflict_do_update(
                index_elements=[PrepStepCounterRow.user_id],
                set_={"last_number": PrepStepCounterRow.last_number + count},
            )
            .returning(PrepStepCounterRow.last_number)
        )
        return int(last or 0) - count + 1


def _step(row: PrepStepRow) -> PrepStep:
    return PrepStep(
        id=StepId(row.id),
        number=row.step_number,
        position=row.position,
        kind=StepKind(row.kind),
        title=row.title,
        minutes=row.minutes,
        details=row.details,
        resources=tuple(Resource(item["title"], item["url"]) for item in row.resources),
        done_at=row.done_at,
        note=row.note,
    )
