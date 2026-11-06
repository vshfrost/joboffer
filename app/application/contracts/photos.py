"""Команди й результати контексту photos: примітиви (значення будує use case)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class PhotoData:
    photo_number: int
    label: str
    width: int
    height: int
    created_at: datetime
    last_used_at: datetime | None


@dataclass(frozen=True, slots=True)
class PhotoLibraryData:
    # Новіші першими.
    photos: tuple[PhotoData, ...]
    suggested_photo_number: int | None
