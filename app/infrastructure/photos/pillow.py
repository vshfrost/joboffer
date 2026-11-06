"""Нормалізація фото на Pillow: адаптер порту `PhotoProcessor`."""

import asyncio
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from domain.photos.errors import photo_too_many_pixels
from domain.photos.photo import (
    MAX_PHOTO_PIXELS,
    MAX_PHOTO_SIDE,
    NewPhoto,
    check_frame,
)
from domain.shared.errors import InvalidValue

FORMATS = ("JPEG", "PNG", "WEBP")
JPEG_QUALITY = 88


class PillowPhotos:
    """Фото для шапки CV — кадр, який користувач обрав у браузері: поворот за EXIF, перевірка
    рамки, не більше MAX_PHOTO_SIDE, JPEG без метаданих (EXIF з GPS телефона в PDF не
    потрапляє). Сам не обрізає."""

    async def normalize(self, data: bytes) -> NewPhoto:
        # Декодування й стиснення вантажать процесор: event loop лишається вільним.
        return await asyncio.to_thread(self._normalize, data)

    def _normalize(self, data: bytes) -> NewPhoto:
        try:
            with Image.open(BytesIO(data), formats=FORMATS) as source:
                # Розмір відомий із заголовка: завелике не декодуємо взагалі.
                if source.width * source.height > MAX_PHOTO_PIXELS:
                    raise photo_too_many_pixels()
                image = ImageOps.exif_transpose(source)
                image.load()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise InvalidValue("file", "Фото — JPEG, PNG або WebP.") from error
        check_frame(image.width, image.height)
        image = _on_white(image)
        image.thumbnail((MAX_PHOTO_SIDE, MAX_PHOTO_SIDE))
        out = BytesIO()
        # Без exif= / icc_profile= Pillow не пише метадані.
        image.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return NewPhoto(data=out.getvalue(), width=image.width, height=image.height)


def _on_white(image: Image.Image) -> Image.Image:
    """RGB; прозорі ділянки PNG / WebP — на білому, а не на чорному."""
    if "A" in image.getbands() or image.mode == "P":
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")
