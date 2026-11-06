"""InterviewKitRepository на Postgres.

Номер версії видає `interview_kit_counters` (наскрізно по вакансіях користувача, номери не
повторюються): апсерт рядка користувача блокує його до кінця транзакції, тож паралельні
збереження одного користувача (а з ними й підрахунок версії вакансії) йдуть по черзі, а скасована
транзакція номер не витрачає. `content` — JSON тієї ж форми, що в v1 (`topic_id` — номер теми
користувача): ETL переносить рядки без перетворень.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.prep.ids import KitId
from domain.prep.kit import (
    InterviewKit,
    KitQuestion,
    KitQuestionKind,
    KitVersion,
    StarStory,
)
from infrastructure.db.jobs.tables import JobRow
from infrastructure.db.prep.tables import InterviewKitCounterRow, InterviewKitRow


class PostgresInterviewKits:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        user_id: UserId,
        kit_id: KitId,
        job_id: JobId,
        kit: InterviewKit,
        now: datetime,
    ) -> KitVersion:
        number = await self._next_number(user_id)
        latest = await self._session.scalar(
            select(func.max(InterviewKitRow.version)).where(
                InterviewKitRow.job_id == job_id.value
            )
        )
        row = InterviewKitRow(
            id=kit_id.value,
            user_id=user_id.value,
            kit_number=number,
            job_id=job_id.value,
            version=(latest or 0) + 1,
            content=_to_json(kit),
            created_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        job_number = await self._session.scalar(
            select(JobRow.job_number).where(JobRow.id == job_id.value)
        )
        return _to_domain(row, int(job_number or 0))

    async def _next_number(self, user_id: UserId) -> int:
        reserved = await self._session.scalar(
            pg_insert(InterviewKitCounterRow)
            .values(user_id=user_id.value, last_number=1)
            .on_conflict_do_update(
                index_elements=[InterviewKitCounterRow.user_id],
                set_={"last_number": InterviewKitCounterRow.last_number + 1},
            )
            .returning(InterviewKitCounterRow.last_number)
        )
        return int(reserved or 0)

    async def latest(self, user_id: UserId, job_id: JobId) -> KitVersion | None:
        found = (
            await self._session.execute(
                select(InterviewKitRow, JobRow.job_number)
                .join(JobRow, JobRow.id == InterviewKitRow.job_id)
                .where(
                    InterviewKitRow.user_id == user_id.value,
                    InterviewKitRow.job_id == job_id.value,
                )
                .order_by(InterviewKitRow.version.desc())
                .limit(1)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if found is None:
            return None
        row, job_number = found
        return _to_domain(row, job_number)


def _to_domain(row: InterviewKitRow, job_number: int) -> KitVersion:
    return KitVersion(
        id=KitId(row.id),
        number=row.kit_number,
        job_number=job_number,
        version=row.version,
        kit=_from_json(row.content),
        created_at=row.created_at,
    )


def _to_json(kit: InterviewKit) -> dict[str, object]:
    return {
        "questions": [
            {
                "kind": question.kind.value,
                "question": question.question,
                "topic_id": question.topic_number,
            }
            for question in kit.questions
        ],
        "stories": [
            {
                "title": story.title,
                "situation": story.situation,
                "task": story.task,
                "action": story.action,
                "result": story.result,
                "fact_ids": list(story.fact_ids),
            }
            for story in kit.stories
        ],
        "company_questions": list(kit.company_questions),
    }


def _from_json(data: dict[str, Any]) -> InterviewKit:
    return InterviewKit(
        questions=tuple(
            KitQuestion(
                KitQuestionKind(question["kind"]),
                question["question"],
                question["topic_id"],
            )
            for question in data["questions"]
        ),
        stories=tuple(
            StarStory(
                story["title"],
                story["situation"],
                story["task"],
                story["action"],
                story["result"],
                tuple(story["fact_ids"]),
            )
            for story in data["stories"]
        ),
        company_questions=tuple(data["company_questions"]),
    )
