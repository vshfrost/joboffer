"""Порти контексту photos: нормалізація фото, репозиторій і unit of work, що його відкриває.

Фото — за номером у межах користувача (`number`); чуже й неіснуюче не відрізняються.
"""

from datetime import datetime
from typing import Protocol

from application.ports.unit_of_work import UnitOfWork
from domain.identity.ids import UserId
from domain.photos.ids import PhotoId
from domain.photos.photo import NewPhoto, Photo, StoredPhoto


class PhotoProcessor(Protocol):
    async def normalize(self, data: bytes) -> NewPhoto:
        """JPEG під рамку шапки CV без метаданих (EXIF, GPS). `InvalidValue` — не картинка
        чи кадр не під рамку."""
        ...


class PhotoRepository(Protocol):
    async def add(
        self,
        user_id: UserId,
        photo_id: PhotoId,
        photo: NewPhoto,
        now: datetime,
        number: int | None = None,
    ) -> Photo:
        """`number` не задано — наступний номер користувача (з 1); задано явно (перенос з v1) —
        лічильник не відстає від нього."""
        ...

    async def all(self, user_id: UserId) -> list[Photo]:
        """Фото користувача без байтів, новіші першими; `last_used_at` — з його документів."""
        ...

    async def get(self, user_id: UserId, number: int) -> StoredPhoto | None:
        """Фото з байтами; None — нема чи чуже."""
        ...

    async def data(self, user_id: UserId, number: int) -> bytes | None:
        """JPEG фото; None — нема чи чуже."""
        ...

    async def delete(self, user_id: UserId, number: int) -> bool:
        """False — нема чи чуже. Документи з цим фото лишаються (`photo_id` стає NULL)."""
        ...


class PhotoUnitOfWork(UnitOfWork, Protocol):
    @property
    def photos(self) -> PhotoRepository: ...
