"""Помилки фото."""

from domain.photos.photo import MAX_UPLOAD_BYTES
from domain.shared.errors import InvalidValue


def photo_too_large() -> InvalidValue:
    """Файл більший за ліміт завантаження."""
    return InvalidValue("file", f"Фото — до {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ.")
