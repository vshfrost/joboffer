"""FactRepository і OriginalCvRepository на Postgres.

Номер факту видає `fact_counters`: апсерт рядка користувача блокує його до кінця транзакції,
тож паралельні додавання одного користувача йдуть по черзі, а скасована транзакція номер не
витрачає. Явний номер (перенос з v1) лічильник не відсуває назад.
"""

from collections.abc import Collection
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.facts.fact import (
    MAX_FACT_NUMBER,
    Fact,
    FactKind,
    FactSource,
    NewFact,
    NewOriginalCv,
    OriginalCv,
)
from domain.facts.ids import FactId
from domain.identity.ids import UserId
from infrastructure.db.facts.tables import FactCounterRow, FactRow, OriginalCvRow
from infrastructure.db.jobs.tables import JobRow


class PostgresFacts:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_additions(self, user_id: UserId) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:user, 0))"),
            {"user": f"facts:{user_id}"},
        )

    async def find_duplicate(self, user_id: UserId, fingerprint: str) -> int | None:
        return await self._session.scalar(
            select(FactRow.fact_number).where(
                FactRow.user_id == user_id.value, FactRow.text_hash == fingerprint
            )
        )

    async def add(
        self,
        user_id: UserId,
        fact_id: FactId,
        fact: NewFact,
        now: datetime,
        number: int | None = None,
    ) -> Fact:
        given = await self._reserve_number(user_id, number)
        row = FactRow(
            id=fact_id.value,
            user_id=user_id.value,
            fact_number=given,
            kind=fact.kind.value,
            text=fact.text,
            text_hash=fact.fingerprint,
            confirmed=fact.confirmed,
            source=fact.source.value,
            job_uuid=await self._job_uuid(user_id, fact.job_number),
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _fact(row)

    async def _job_uuid(self, user_id: UserId, number: int | None) -> UUID | None:
        if number is None:
            return None
        return await self._session.scalar(
            select(JobRow.id).where(
                JobRow.user_id == user_id.value, JobRow.job_number == number
            )
        )

    async def _reserve_number(self, user_id: UserId, explicit: int | None) -> int:
        if explicit is None:
            counter = pg_insert(FactCounterRow).values(
                user_id=user_id.value, last_number=1
            )
            update_to = FactCounterRow.last_number + 1
        else:
            counter = pg_insert(FactCounterRow).values(
                user_id=user_id.value, last_number=max(explicit, 0)
            )
            update_to = func.greatest(FactCounterRow.last_number, explicit)
        reserved = await self._session.scalar(
            counter.on_conflict_do_update(
                index_elements=[FactCounterRow.user_id], set_={"last_number": update_to}
            ).returning(FactCounterRow.last_number)
        )
        return explicit if explicit is not None else int(reserved or 0)

    async def all(self, user_id: UserId) -> list[Fact]:
        rows = await self._session.scalars(
            select(FactRow)
            .where(FactRow.user_id == user_id.value)
            .order_by(FactRow.fact_number)
            .execution_options(populate_existing=True)
        )
        return [_fact(row) for row in rows]

    async def get(self, user_id: UserId, number: int) -> Fact | None:
        if not 1 <= number <= MAX_FACT_NUMBER:
            return None
        row = await self._session.scalar(
            select(FactRow)
            .where(FactRow.user_id == user_id.value, FactRow.fact_number == number)
            .execution_options(populate_existing=True)
        )
        return None if row is None else _fact(row)

    async def replace(
        self, user_id: UserId, number: int, fact: NewFact, now: datetime
    ) -> Fact:
        await self._session.execute(
            update(FactRow)
            .where(FactRow.user_id == user_id.value, FactRow.fact_number == number)
            .values(
                kind=fact.kind.value,
                text=fact.text,
                text_hash=fact.fingerprint,
                confirmed=False,
                updated_at=now,
            )
        )
        # Use case перевірив, що факт є; інакше `NoResultFound` — помилка програми.
        found = await self._session.execute(
            select(FactRow)
            .where(FactRow.user_id == user_id.value, FactRow.fact_number == number)
            .execution_options(populate_existing=True)
        )
        return _fact(found.scalar_one())

    async def delete(self, user_id: UserId, number: int) -> None:
        await self._session.execute(
            delete(FactRow).where(
                FactRow.user_id == user_id.value, FactRow.fact_number == number
            )
        )

    async def confirm(
        self, user_id: UserId, numbers: Collection[int], now: datetime
    ) -> None:
        await self._session.execute(
            update(FactRow)
            .where(
                FactRow.user_id == user_id.value, FactRow.fact_number.in_(list(numbers))
            )
            .values(confirmed=True, updated_at=now)
        )


class PostgresOriginalCvs:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UserId) -> OriginalCv | None:
        row = await self._session.get(
            OriginalCvRow, user_id.value, populate_existing=True
        )
        if row is None:
            return None
        return OriginalCv(
            text=row.text, file_name=row.file_name, saved_at=row.updated_at
        )

    async def save(self, user_id: UserId, cv: NewOriginalCv, now: datetime) -> None:
        values = {"file_name": cv.file_name, "text": cv.text, "updated_at": now}
        await self._session.execute(
            pg_insert(OriginalCvRow)
            .values(user_id=user_id.value, **values)
            .on_conflict_do_update(index_elements=[OriginalCvRow.user_id], set_=values)
        )


def _fact(row: FactRow) -> Fact:
    return Fact(
        id=FactId(row.id),
        number=row.fact_number,
        kind=FactKind(row.kind),
        text=row.text,
        confirmed=row.confirmed,
        created_at=row.created_at,
        updated_at=row.updated_at,
        source=FactSource(row.source),
        job_id=row.job_number,
    )
