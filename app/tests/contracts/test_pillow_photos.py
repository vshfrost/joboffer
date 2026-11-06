"""PillowPhotos: кадр, який обрав користувач, → JPEG без метаданих. Усі зображення згенеровані."""

import pytest
from anyio.from_thread import BlockingPortal
from PIL import ExifTags, Image

from domain.photos.photo import NewPhoto
from domain.shared.errors import InvalidValue
from infrastructure.photos.pillow import PillowPhotos
from tests.support.images import (
    FRAME,
    HALF_FRAME,
    decoded,
    image,
    jpeg,
    pixel,
    transparent_png,
)

NOT_AN_IMAGE = "Фото — JPEG, PNG або WebP."
BAD_FRAME = "Фото має бути в пропорціях рамки CV (858 × 960): обери область у редакторі на сторінці профілю."
TOO_NARROW = "Обрана область вужча за 300 px — візьми більшу або фото кращої якості."


def normalize(portal: BlockingPortal, data: bytes) -> NewPhoto:
    return portal.call(PillowPhotos().normalize, data)


def rejected(portal: BlockingPortal, data: bytes) -> InvalidValue:
    with pytest.raises(InvalidValue) as error:
        normalize(portal, data)
    return error.value


def test_a_frame_in_the_header_proportions_becomes_a_jpeg_of_the_same_size(
    portal: BlockingPortal,
) -> None:
    photo = normalize(portal, jpeg(*HALF_FRAME))
    result = decoded(photo.data)
    assert (result.format, result.size) == ("JPEG", HALF_FRAME)
    assert (photo.width, photo.height) == HALF_FRAME


def test_a_small_but_wide_enough_frame_is_kept_as_is(portal: BlockingPortal) -> None:
    photo = normalize(portal, jpeg(300, 336))
    assert (photo.width, photo.height) == (300, 336)


def test_a_frame_in_other_proportions_is_rejected_with_the_v1_text(
    portal: BlockingPortal,
) -> None:
    error = rejected(portal, jpeg(1000, 1000))
    assert (error.field, error.message) == ("file", BAD_FRAME)


def test_a_frame_narrower_than_300_px_is_rejected_with_the_v1_text(
    portal: BlockingPortal,
) -> None:
    error = rejected(portal, jpeg(299, 335))
    assert (error.field, error.message) == ("file", TOO_NARROW)


def test_the_full_size_frame_of_the_header_is_scaled_down_to_900_px(
    portal: BlockingPortal,
) -> None:
    photo = normalize(portal, jpeg(*FRAME))
    assert (photo.width, photo.height) == (804, 900)


def test_a_side_over_900_px_is_scaled_down_keeping_the_proportions(
    portal: BlockingPortal,
) -> None:
    photo = normalize(portal, jpeg(1716, 1920))
    assert photo.height == 900
    assert photo.width == pytest.approx(804, abs=1)
    assert decoded(photo.data).size == (photo.width, photo.height)


def test_a_phone_photo_is_rotated_by_its_exif_orientation(
    portal: BlockingPortal,
) -> None:
    # Пікселі лежать боком (480 × 429), орієнтація 6 каже повернути: кадр стає 429 × 480.
    photo = normalize(portal, jpeg(480, 429, orientation=6))
    assert (photo.width, photo.height) == HALF_FRAME
    assert decoded(photo.data).size == HALF_FRAME


def test_the_result_carries_no_metadata_at_all(portal: BlockingPortal) -> None:
    photo = normalize(portal, jpeg(*HALF_FRAME, orientation=1, gps=True))
    result = decoded(photo.data)
    assert dict(result.getexif()) == {}
    assert result.getexif().get_ifd(ExifTags.IFD.GPSInfo) == {}
    assert b"Exif" not in photo.data
    assert b"TestCam" not in photo.data
    assert not {"exif", "icc_profile", "comment"} & set(result.info)


def test_a_transparent_png_goes_onto_a_white_background(
    portal: BlockingPortal,
) -> None:
    photo = normalize(portal, transparent_png(*FRAME))
    assert min(pixel(photo.data, 5, 5)) >= 250
    assert min(pixel(photo.data, 400, 500)) >= 250


@pytest.mark.parametrize("fmt", ["PNG", "WEBP", "JPEG"])
def test_jpeg_png_and_webp_are_accepted(portal: BlockingPortal, fmt: str) -> None:
    photo = normalize(portal, image(*HALF_FRAME, fmt))  # type: ignore[arg-type]
    assert decoded(photo.data).format == "JPEG"


@pytest.mark.parametrize("fmt", ["GIF", "BMP"])
def test_other_image_formats_are_rejected(portal: BlockingPortal, fmt: str) -> None:
    error = rejected(portal, image(*HALF_FRAME, fmt))  # type: ignore[arg-type]
    assert (error.field, error.message) == ("file", NOT_AN_IMAGE)


def test_text_with_a_photo_name_is_not_an_image(portal: BlockingPortal) -> None:
    assert rejected(portal, b"this is just text, photo.jpg").message == NOT_AN_IMAGE


def test_a_truncated_jpeg_is_not_an_image(portal: BlockingPortal) -> None:
    assert rejected(portal, jpeg(*FRAME)[:200]).message == NOT_AN_IMAGE


def test_an_image_too_big_to_decode_safely_is_not_an_image(
    portal: BlockingPortal, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    assert rejected(portal, jpeg(*FRAME)).message == NOT_AN_IMAGE
