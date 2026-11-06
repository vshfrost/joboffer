"""Згенеровані тестові зображення (справжніх фото в репо нема): Pillow лише в тестах з адаптерами."""

from io import BytesIO
from typing import Literal

from PIL import ExifTags, Image

# Кадр рівно під рамку шапки CV (858 × 960) і його половина.
FRAME = (858, 960)
HALF_FRAME = (429, 480)
RED = (200, 30, 30)


def jpeg(
    width: int,
    height: int,
    *,
    orientation: int | None = None,
    gps: bool = False,
    color: tuple[int, int, int] = RED,
) -> bytes:
    """JPEG; `orientation` і `gps` кладуть у нього EXIF (поворот, координати, виробник камери)."""
    exif = Image.Exif()
    if orientation is not None:
        exif[ExifTags.Base.Orientation] = orientation
    if gps:
        exif[ExifTags.Base.Make] = "TestCam"
        exif[ExifTags.Base.GPSInfo] = {
            1: "N",
            2: (39.0, 28.0, 0.0),
            3: "W",
            4: (0.0, 22.0, 0.0),
        }
    out = BytesIO()
    Image.new("RGB", (width, height), color).save(out, "JPEG", exif=exif)
    return out.getvalue()


def transparent_png(width: int, height: int) -> bytes:
    """PNG, цілком прозорий (RGBA 0,0,0,0): на чорному він виглядав би чорним."""
    out = BytesIO()
    Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(out, "PNG")
    return out.getvalue()


def image(
    width: int, height: int, fmt: Literal["PNG", "WEBP", "GIF", "BMP", "JPEG"]
) -> bytes:
    out = BytesIO()
    Image.new("RGB", (width, height), RED).save(out, fmt)
    return out.getvalue()


def decoded(data: bytes) -> Image.Image:
    picture = Image.open(BytesIO(data))
    picture.load()
    return picture


def pixel(data: bytes, x: int, y: int) -> tuple[int, int, int]:
    """RGB-колір точки зображення."""
    red, green, blue = decoded(data).convert("RGB").getpixel((x, y))  # type: ignore[misc]
    return red, green, blue
