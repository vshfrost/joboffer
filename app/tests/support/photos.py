"""In-memory адаптери photos для core-тестів: та сама семантика, що в Postgres (номери, власник, commit)."""

from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self

from domain.identity.ids import UserId
from domain.photos.ids import PhotoId
from domain.photos.photo import NewPhoto, Photo, StoredPhoto
from domain.shared.errors import InvalidValue

NOT_AN_IMAGE = b"not-an-image"
FRAME_ERROR = "Фото має бути в пропорціях рамки CV (858 × 960): обери область у редакторі на сторінці профілю."


@dataclass
class Store:
    photos: dict[tuple[UserId, int], Photo] = field(default_factory=dict)
    data: dict[tuple[UserId, int], bytes] = field(default_factory=dict)
    counters: dict[UserId, int] = field(default_factory=dict)
    ids: dict[tuple[UserId, int], PhotoId] = field(default_factory=dict)

    def copy(self) -> Self:
        return type(self)(
            dict(self.photos), dict(self.data), dict(self.counters), dict(self.ids)
        )

    def owner_of(self, photo_id: PhotoId) -> tuple[UserId, int]:
        return next(key for key, known in self.ids.items() if known == photo_id)

    def use(self, user_id: UserId, number: int, when: datetime) -> None:
        """Фото пішло в CV: так `last_used_at` з'являється у Postgres (з документів)."""
        key = (user_id, number)
        photo = self.photos[key]
        used = photo.last_used_at
        newest = when if used is None or when > used else used
        self.photos[key] = Photo(
            photo.number,
            photo.label,
            photo.width,
            photo.height,
            photo.created_at,
            newest,
        )


class FakeProcessor:
    """Нормалізація без Pillow: `NOT_AN_IMAGE` — помилка, решта стає кадром 858 × 960."""

    def __init__(self) -> None:
        self.calls: list[bytes] = []

    async def normalize(self, data: bytes) -> NewPhoto:
        self.calls.append(data)
        if data == NOT_AN_IMAGE:
            raise InvalidValue("file", "Фото — JPEG, PNG або WebP.")
        return NewPhoto(data=b"jpeg:" + data[:20], width=858, height=960)


class InMemoryPhotos:
    def __init__(self, store: Store) -> None:
        self._s = store

    async def add(
        self,
        user_id: UserId,
        photo_id: PhotoId,
        photo: NewPhoto,
        now: datetime,
        number: int | None = None,
    ) -> Photo:
        counter = self._s.counters.get(user_id, 0)
        given = counter + 1 if number is None else number
        self._s.counters[user_id] = max(counter, given)
        key = (user_id, given)
        added = Photo(given, photo.label, photo.width, photo.height, now, None)
        self._s.photos[key] = added
        self._s.data[key] = photo.data
        self._s.ids[key] = photo_id
        return added

    async def all(self, user_id: UserId) -> list[Photo]:
        mine = [p for (owner, _), p in self._s.photos.items() if owner == user_id]
        return sorted(mine, key=lambda p: (p.created_at, p.number), reverse=True)

    async def get(self, user_id: UserId, number: int) -> StoredPhoto | None:
        key = (user_id, number)
        if key not in self._s.photos:
            return None
        return StoredPhoto(self._s.ids[key], number, self._s.data[key])

    async def data(self, user_id: UserId, number: int) -> bytes | None:
        return self._s.data.get((user_id, number))

    async def delete(self, user_id: UserId, number: int) -> bool:
        key = (user_id, number)
        if key not in self._s.photos:
            return False
        del self._s.photos[key]
        del self._s.data[key]
        del self._s.ids[key]
        return True


class InMemoryPhotoUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(self, store: Store) -> None:
        self._store = store
        self._staged: Store | None = None

    @property
    def photos(self) -> InMemoryPhotos:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemoryPhotos(self._staged)

    async def __aenter__(self) -> Self:
        self._staged = self._store.copy()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        self._store.photos = self._staged.photos
        self._store.data = self._staged.data
        self._store.counters = self._staged.counters
        self._store.ids = self._staged.ids
