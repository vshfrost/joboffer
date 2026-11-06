"""PrepQuestionRepository на Postgres.

Номер питання видає `prep_question_counters` (наскрізно по темах користувача, номери не
повторюються): апсерт рядка користувача блокує його до кінця транзакції, а скасована транзакція
номер не витрачає. Додавання питань одного користувача йдуть по черзі (advisory-замок): перевірка
дубля й вставка не б'ються з паралельним збереженням того самого питання; дубль номера не
витрачає. Спроби відповідей лишаються в `prep_answers` — по рядку на кожну.
"""

from datetime import datetime

from sqlalchemy import ColumnElement, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.identity.ids import UserId
from domain.prep.ids import AnswerId, QuestionId
from domain.prep.quiz import Answer, NewQuestion, PastAnswer, PrepQuestion, Schedule
from infrastructure.db.prep.tables import (
    PrepAnswerRow,
    PrepQuestionCounterRow,
    PrepQuestionRow,
    PrepTopicRow,
)


class PostgresPrepQuestions:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(
        self, user_id: UserId, topic_number: int | None = None
    ) -> list[PrepQuestion]:
        wanted = [PrepQuestionRow.user_id == user_id.value]
        if topic_number is not None:
            wanted.append(PrepTopicRow.topic_number == topic_number)
        return await self._questions(*wanted)

    async def get(self, user_id: UserId, number: int) -> PrepQuestion | None:
        found = await self._questions(
            PrepQuestionRow.user_id == user_id.value,
            PrepQuestionRow.question_number == number,
        )
        return found[0] if found else None

    async def _questions(self, *wanted: ColumnElement[bool]) -> list[PrepQuestion]:
        rows = await self._session.execute(
            select(PrepQuestionRow, PrepTopicRow.topic_number, PrepTopicRow.title)
            .join(PrepTopicRow, PrepTopicRow.id == PrepQuestionRow.topic_id)
            .where(*wanted)
            .order_by(PrepQuestionRow.question_number)
            .execution_options(populate_existing=True)
        )
        return [
            PrepQuestion(
                id=QuestionId(row.id),
                number=row.question_number,
                topic_number=topic_number,
                topic_title=topic_title,
                question=row.question,
                answer_points=tuple(row.answer_points),
                box=row.box,
                due_on=row.due_on,
                created_at=row.created_at,
            )
            for row, topic_number, topic_title in rows
        ]

    async def add(  # noqa: PLR0913, PLR0917
        self,
        user_id: UserId,
        question_id: QuestionId,
        topic_number: int,
        question: NewQuestion,
        schedule: Schedule,
        now: datetime,
    ) -> int | None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:user, 0))"),
            {"user": f"prep_questions:{user_id}"},
        )
        # Тему перевіряє use case: тут вона є.
        topic_id = (
            await self._session.execute(
                select(PrepTopicRow.id).where(
                    PrepTopicRow.user_id == user_id.value,
                    PrepTopicRow.topic_number == topic_number,
                )
            )
        ).scalar_one()
        duplicate = await self._session.scalar(
            select(PrepQuestionRow.id).where(
                PrepQuestionRow.topic_id == topic_id,
                PrepQuestionRow.question_hash == question.fingerprint,
            )
        )
        if duplicate is not None:
            return None
        number = await self._next_number(user_id)
        self._session.add(
            PrepQuestionRow(
                id=question_id.value,
                user_id=user_id.value,
                topic_id=topic_id,
                question_number=number,
                question=question.question,
                question_hash=question.fingerprint,
                answer_points=list(question.answer_points),
                box=schedule.box,
                due_on=schedule.due_on,
                created_at=now,
            )
        )
        await self._session.flush()
        return number

    async def _next_number(self, user_id: UserId) -> int:
        reserved = await self._session.scalar(
            pg_insert(PrepQuestionCounterRow)
            .values(user_id=user_id.value, last_number=1)
            .on_conflict_do_update(
                index_elements=[PrepQuestionCounterRow.user_id],
                set_={"last_number": PrepQuestionCounterRow.last_number + 1},
            )
            .returning(PrepQuestionCounterRow.last_number)
        )
        return int(reserved or 0)

    async def record(  # noqa: PLR0913, PLR0917
        self,
        user_id: UserId,
        answer_id: AnswerId,
        number: int,
        answer: Answer,
        schedule: Schedule,
        now: datetime,
    ) -> None:
        # Питання перевіряє use case: тут воно є.
        question_id = (
            await self._session.execute(
                update(PrepQuestionRow)
                .where(
                    PrepQuestionRow.user_id == user_id.value,
                    PrepQuestionRow.question_number == number,
                )
                .values(box=schedule.box, due_on=schedule.due_on)
                .returning(PrepQuestionRow.id)
                .execution_options(synchronize_session=False)
            )
        ).scalar_one()
        self._session.add(
            PrepAnswerRow(
                id=answer_id.value,
                question_id=question_id,
                grade=answer.grade,
                answer=answer.answer,
                feedback=answer.feedback,
                box=schedule.box,
                answered_at=now,
            )
        )
        await self._session.flush()

    async def answers(self, user_id: UserId, number: int) -> list[PastAnswer]:
        rows = await self._session.scalars(
            select(PrepAnswerRow)
            .join(PrepQuestionRow, PrepQuestionRow.id == PrepAnswerRow.question_id)
            .where(
                PrepQuestionRow.user_id == user_id.value,
                PrepQuestionRow.question_number == number,
            )
            .order_by(PrepAnswerRow.answered_at, PrepAnswerRow.id)
            .execution_options(populate_existing=True)
        )
        return [
            PastAnswer(row.grade, row.answer, row.feedback, row.box, row.answered_at)
            for row in rows
        ]
