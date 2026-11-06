"""GapAnswerRepository на Postgres.

Відповідь — одна на текст прогалини в межах вакансії (`gap_hash` — відбиток тексту без регістру
й зайвих пробілів): повторна замінює рядок, перший `id` лишається, а факти переписуються.
Факти зберігаються за номером користувача, у базі — зв'язком з UUID факту.
"""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.analysis.gap_answer import GapAnswer
from domain.analysis.ids import GapAnswerId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.shared.fingerprint import text_fingerprint
from infrastructure.db.analysis.tables import GapAnswerFactRow, GapAnswerRow
from infrastructure.db.facts.tables import FactRow


class PostgresGapAnswers:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def for_job(self, user_id: UserId, job_id: JobId) -> list[GapAnswer]:
        rows = (
            await self._session.scalars(
                select(GapAnswerRow)
                .where(
                    GapAnswerRow.user_id == user_id.value,
                    GapAnswerRow.job_id == job_id.value,
                )
                .order_by(GapAnswerRow.answered_at, GapAnswerRow.gap)
                .execution_options(populate_existing=True)
            )
        ).all()
        linked = await self._session.execute(
            select(GapAnswerFactRow.gap_answer_id, FactRow.fact_number)
            .join(FactRow, FactRow.id == GapAnswerFactRow.fact_id)
            .where(GapAnswerFactRow.gap_answer_id.in_([row.id for row in rows]))
            .order_by(GapAnswerFactRow.position)
        )
        numbers: dict[object, list[int]] = {}
        for answer_id, number in linked:
            numbers.setdefault(answer_id, []).append(number)
        return [
            GapAnswer(
                row.gap,
                row.has_experience,
                tuple(numbers.get(row.id, ())),
                row.answered_at,
            )
            for row in rows
        ]

    async def save(
        self,
        user_id: UserId,
        answer_id: GapAnswerId,
        job_id: JobId,
        answer: GapAnswer,
    ) -> None:
        values = {
            "gap": answer.gap,
            "has_experience": answer.has_experience,
            "answered_at": answer.answered_at,
        }
        stored = await self._session.scalar(
            pg_insert(GapAnswerRow)
            .values(
                id=answer_id.value,
                user_id=user_id.value,
                job_id=job_id.value,
                gap_hash=text_fingerprint(answer.gap),
                **values,
            )
            .on_conflict_do_update(
                index_elements=[GapAnswerRow.job_id, GapAnswerRow.gap_hash], set_=values
            )
            .returning(GapAnswerRow.id)
        )
        await self._session.execute(
            delete(GapAnswerFactRow).where(GapAnswerFactRow.gap_answer_id == stored)
        )
        facts = {
            number: fact_id
            for fact_id, number in await self._session.execute(
                select(FactRow.id, FactRow.fact_number).where(
                    FactRow.user_id == user_id.value,
                    FactRow.fact_number.in_(answer.fact_numbers),
                )
            )
        }
        self._session.add_all(
            GapAnswerFactRow(
                gap_answer_id=stored, fact_id=facts[number], position=index
            )
            for index, number in enumerate(answer.fact_numbers)
        )
        await self._session.flush()
