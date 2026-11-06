"""Фото для шапки CV: рамка 858 × 960, мінімальна ширина, що пропонувати за замовчуванням."""

from datetime import UTC, datetime, timedelta

import pytest

from domain.photos.photo import (
    MAX_LABEL_LENGTH,
    MAX_PHOTO_SIDE,
    MAX_UPLOAD_BYTES,
    MIN_PHOTO_WIDTH,
    NewPhoto,
    Photo,
    check_frame,
    suggested_photo,
)
from domain.shared.errors import InvalidValue

BAD_FRAME = "Фото має бути в пропорціях рамки CV (858 × 960): обери область у редакторі на сторінці профілю."
TOO_NARROW = "Обрана область вужча за 300 px — візьми більшу або фото кращої якості."
T0 = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def photo(
    number: int, created: int = 0, used: int | None = None, label: str = ""
) -> Photo:
    return Photo(
        number=number,
        label=label,
        width=858,
        height=960,
        created_at=T0 + timedelta(days=created),
        last_used_at=None if used is None else T0 + timedelta(days=used),
    )


def test_the_limits_are_the_v1_ones_except_the_upload_size() -> None:
    assert MAX_UPLOAD_BYTES == 5 * 1024 * 1024
    assert MAX_LABEL_LENGTH == 100
    assert MAX_PHOTO_SIDE == 900
    assert MIN_PHOTO_WIDTH == 300


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (858, 960),
        (429, 480),
        (300, 336),
        (858, 965),  # у межах ±1 %
        (865, 960),
    ],
)
def test_a_frame_in_the_header_proportions_passes(width: int, height: int) -> None:
    check_frame(width, height)


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (500, 500),
        (960, 858),
        (858, 970),  # трохи за межею ±1 %
        (900, 960),
    ],
)
def test_a_frame_in_other_proportions_is_rejected_with_the_v1_text(
    width: int, height: int
) -> None:
    with pytest.raises(InvalidValue) as error:
        check_frame(width, height)
    assert error.value.message == BAD_FRAME
    assert error.value.field == "file"


@pytest.mark.parametrize(("width", "height"), [(299, 335), (100, 112)])
def test_a_proportional_frame_narrower_than_300_px_is_rejected_with_the_v1_text(
    width: int, height: int
) -> None:
    with pytest.raises(InvalidValue) as error:
        check_frame(width, height)
    assert error.value.message == TOO_NARROW
    assert error.value.field == "file"


def test_no_photos_suggest_nothing() -> None:
    assert suggested_photo([]) is None


def test_without_a_used_photo_the_newest_is_suggested() -> None:
    older, newer = photo(1, created=0), photo(2, created=3)
    assert suggested_photo([older, newer]) == newer


def test_the_last_used_photo_beats_a_newer_unused_one() -> None:
    used, newer = photo(1, created=0, used=5), photo(2, created=9)
    assert suggested_photo([used, newer]) == used


def test_among_used_photos_the_most_recently_used_is_suggested() -> None:
    first, second = photo(1, used=2), photo(2, used=7)
    assert suggested_photo([first, second]) == second


def test_equal_times_are_broken_by_the_higher_number() -> None:
    first, second = photo(1, created=1), photo(2, created=1)
    assert suggested_photo([first, second]) == second


def test_a_new_photo_is_checked_against_the_frame() -> None:
    with pytest.raises(InvalidValue) as error:
        NewPhoto(data=b"x", width=500, height=500)
    assert error.value.message == BAD_FRAME


def test_a_label_of_100_characters_is_kept_and_101_is_rejected() -> None:
    assert (
        NewPhoto(data=b"x", width=858, height=960, label="я" * 100).label == "я" * 100
    )
    with pytest.raises(InvalidValue) as error:
        NewPhoto(data=b"x", width=858, height=960, label="я" * 101)
    assert (error.value.field, error.value.message) == (
        "label",
        "Підпис фото — до 100 символів.",
    )
