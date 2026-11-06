"""PhotoRepository на Postgres.

Номер фото видає `photo_counters`: апсерт рядка користувача блокує його до кінця транзакції,
тож паралельні завантаження одного користувача йдуть по черзі, а скасована транзакція номер не
витрачає. Явний номер (перенос з v1) лічильник не відсуває назад.
"""

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.identity.ids import UserId
from domain.photos.ids import PhotoId
from domain.photos.photo import MAX_PHOTO_NUMBER, NewPhoto, Photo, StoredPhoto
from infrastructure.db.documents.tables import DocumentRow
from infrastructure.db.photos.tables import PhotoCounterRow, PhotoRow


class PostgresPhotos:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        user_id: UserId,
        photo_id: PhotoId,
        photo: NewPhoto,
        now: datetime,
        number: int | None = None,
    ) -> Photo:
        given = await self._reserve_number(user_id, number)
        self._session.add(
            PhotoRow(
                id=photo_id.value,
                user_id=user_id.value,
                photo_number=given,
                label=photo.label,
                data=photo.data,
                width=photo.width,
                height=photo.height,
                created_at=now,
            )
        )
        await self._session.flush()
        return Photo(given, photo.label, photo.width, photo.height, now, None)

    async def _reserve_number(self, user_id: UserId, explicit: int | None) -> int:
        if explicit is None:
            counter = pg_insert(PhotoCounterRow).values(
                user_id=user_id.value, last_number=1
            )
            update_to = PhotoCounterRow.last_number + 1
        else:
            counter = pg_insert(PhotoCounterRow).values(
                user_id=user_id.value, last_number=max(explicit, 0)
            )
            update_to = func.greatest(PhotoCounterRow.last_number, explicit)
        reserved = await self._session.scalar(
            counter.on_conflict_do_update(
                index_elements=[PhotoCounterRow.user_id],
                set_={"last_number": update_to},
            ).returning(PhotoCounterRow.last_number)
        )
        return explicit if explicit is not None else int(reserved or 0)

    async def all(self, user_id: UserId) -> list[Photo]:
        last_used = (
            select(func.max(DocumentRow.created_at))
            .where(DocumentRow.photo_id == PhotoRow.id)
            .scalar_subquery()
        )
        rows = await self._session.execute(
            select(
                PhotoRow.photo_number,
                PhotoRow.label,
                PhotoRow.width,
                PhotoRow.height,
                PhotoRow.created_at,
                last_used,
            )
            .where(PhotoRow.user_id == user_id.value)
            .order_by(PhotoRow.created_at.desc(), PhotoRow.photo_number.desc())
        )
        return [Photo(*row) for row in rows]

    async def get(self, user_id: UserId, number: int) -> StoredPhoto | None:
        if not 1 <= number <= MAX_PHOTO_NUMBER:
            return None
        row = (
            await self._session.execute(
                select(PhotoRow.id, PhotoRow.data).where(
                    PhotoRow.user_id == user_id.value, PhotoRow.photo_number == number
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return StoredPhoto(PhotoId(row.id), number, row.data)

    async def data(self, user_id: UserId, number: int) -> bytes | None:
        if not 1 <= number <= MAX_PHOTO_NUMBER:
            return None
        return await self._session.scalar(
            select(PhotoRow.data).where(
                PhotoRow.user_id == user_id.value, PhotoRow.photo_number == number
            )
        )

    async def delete(self, user_id: UserId, number: int) -> bool:
        if not 1 <= number <= MAX_PHOTO_NUMBER:
            return False
        deleted = await self._session.scalar(
            delete(PhotoRow)
            .where(PhotoRow.user_id == user_id.value, PhotoRow.photo_number == number)
            .returning(PhotoRow.id)
        )
        return deleted is not None
