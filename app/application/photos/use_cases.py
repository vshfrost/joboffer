"""Use cases фото для шапки CV: завантаження (нормалізує адаптер), перелік, читання, видалення.
REST і MCP викликають саме їх — правила в одному місці."""

from collections.abc import Callable

from application.contracts.actor import Actor
from application.contracts.photos import PhotoData, PhotoLibraryData
from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.photos import PhotoProcessor, PhotoUnitOfWork
from domain.photos.errors import photo_too_large
from domain.photos.ids import PhotoId
from domain.photos.photo import MAX_UPLOAD_BYTES, NewPhoto, Photo, suggested_photo
from domain.profile.text import one_line
from domain.shared.errors import InvalidValue, NotFound


class PhotoUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], PhotoUnitOfWork],
        processor: PhotoProcessor,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._processor = processor
        self._clock = clock
        self._ids = ids

    async def add_photo(self, actor: Actor, data: bytes, label: str = "") -> PhotoData:
        """Нормалізує й зберігає фото. `InvalidValue` — нічого не збережено."""
        if not data:
            raise InvalidValue("file", "Файл порожній — вибери фото.")
        if len(data) > MAX_UPLOAD_BYTES:
            raise photo_too_large()
        normalized = await self._processor.normalize(data)
        photo = NewPhoto(
            data=normalized.data,
            width=normalized.width,
            height=normalized.height,
            label=one_line(label),
        )
        async with self._unit_of_work() as uow:
            added = await uow.photos.add(
                actor.user_id, PhotoId(self._ids.new()), photo, self._clock.now()
            )
            await uow.commit()
        return photo_data(added)

    async def list_photos(self, actor: Actor) -> PhotoLibraryData:
        """Фото користувача, новіші першими, і номер того, що пропонувати для CV."""
        async with self._unit_of_work() as uow:
            photos = await uow.photos.all(actor.user_id)
        suggested = suggested_photo(photos)
        return PhotoLibraryData(
            photos=tuple(photo_data(photo) for photo in photos),
            suggested_photo_number=None if suggested is None else suggested.number,
        )

    async def read_photo(self, actor: Actor, photo_number: int) -> bytes:
        """JPEG фото. `NotFound` — нема чи чуже."""
        async with self._unit_of_work() as uow:
            data = await uow.photos.data(actor.user_id, photo_number)
        if data is None:
            raise _not_found(photo_number)
        return data

    async def delete_photo(self, actor: Actor, photo_number: int) -> None:
        """Видаляє назавжди; збережені документи лишаються. `NotFound` — нема чи чуже."""
        async with self._unit_of_work() as uow:
            if not await uow.photos.delete(actor.user_id, photo_number):
                raise _not_found(photo_number)
            await uow.commit()


def _not_found(number: int) -> NotFound:
    return NotFound(f"Фото #{number} не знайдено.")


def photo_data(photo: Photo) -> PhotoData:
    return PhotoData(
        photo_number=photo.number,
        label=photo.label,
        width=photo.width,
        height=photo.height,
        created_at=photo.created_at,
        last_used_at=photo.last_used_at,
    )
