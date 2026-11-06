"""Фото для шапки CV: користувач тримає кілька в профілі, перед генерацією CV Claude пропонує одне
(або без фото). Область фото користувач обирає сам у браузері; сервер не обрізає, лише
перевіряє, що кадр під рамку шапки."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from domain.photos.ids import PhotoId
from domain.shared.errors import InvalidValue

# Веб вантажить кадр до 900 px заввишки (менше 1 МБ), тож 5 МБ — запас для прямих клієнтів API.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# Стеля декодування: RGB-кадр займає 3 байти на піксель, тож 16 МП — десятки мегабайтів, а не гігабайт.
MAX_PHOTO_PIXELS = 16_000_000
MAX_LABEL_LENGTH = 100
# Рамка фото в шапці CV — пропорції зразка (858 × 960): ширина / висота.
PHOTO_ASPECT = 858 / 960
# Округлення пікселів у редакторі й під час зменшення — не помилка кадру.
ASPECT_TOLERANCE = 0.01
MAX_PHOTO_SIDE = 900
# У рамці шириною 101 pt це ≈ 214 dpi.
MIN_PHOTO_WIDTH = 300
# Номер фото зберігається в int4: більший за нього не існує.
MAX_PHOTO_NUMBER = 2**31 - 1


def check_frame(width: int, height: int) -> None:
    """Кадр під рамку шапки CV: її пропорції і не вужчий за MIN_PHOTO_WIDTH."""
    if abs(width / height - PHOTO_ASPECT) > PHOTO_ASPECT * ASPECT_TOLERANCE:
        raise InvalidValue(
            "file",
            "Фото має бути в пропорціях рамки CV (858 × 960): обери область у редакторі "
            "на сторінці профілю.",
        )
    if width < MIN_PHOTO_WIDTH:
        raise InvalidValue(
            "file",
            f"Обрана область вужча за {MIN_PHOTO_WIDTH} px — візьми більшу або фото "
            "кращої якості.",
        )


@dataclass(frozen=True, slots=True)
class NewPhoto:
    """Фото після нормалізації: JPEG без метаданих, кадр під рамку шапки."""

    data: bytes
    width: int
    height: int
    label: str = ""

    def __post_init__(self) -> None:
        if len(self.label) > MAX_LABEL_LENGTH:
            raise InvalidValue(
                "label", f"Підпис фото — до {MAX_LABEL_LENGTH} символів."
            )
        check_frame(self.width, self.height)


@dataclass(frozen=True, slots=True)
class Photo:
    # Дані (байти) лежать окремо: список фото їх не несе.
    number: int
    label: str
    width: int
    height: int
    created_at: datetime
    # Коли востаннє пішло в CV; None — ще не використовувалось.
    last_used_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class StoredPhoto:
    """Фото з байтами: для рендера CV і для зв'язку документа з фото."""

    id: PhotoId
    number: int
    data: bytes


def suggested_photo(photos: Sequence[Photo]) -> Photo | None:
    """Що пропонувати за замовчуванням: останнє використане в CV, інакше найновіше."""
    used = [photo for photo in photos if photo.last_used_at is not None]
    pool = used or list(photos)
    if not pool:
        return None
    return max(
        pool, key=lambda photo: (photo.last_used_at or photo.created_at, photo.number)
    )
