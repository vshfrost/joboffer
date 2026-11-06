"""Use cases фото: перевірки до нормалізації, підпис, номери, пропозиція, ізоляція користувачів."""

from datetime import timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.photos import PhotoData, PhotoLibraryData
from application.photos.use_cases import PhotoUseCases
from domain.identity.ids import UserId
from domain.shared.errors import InvalidValue, NotFound
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.photos import (
    NOT_AN_IMAGE,
    FakeProcessor,
    InMemoryPhotoUnitOfWork,
    Store,
)

MB = 1024 * 1024
JPEG = b"\xff\xd8 a photo"


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.store = Store()
        self.processor = FakeProcessor()
        self.alice = self._actor()
        self.bob = self._actor()
        self.use_cases = PhotoUseCases(
            lambda: InMemoryPhotoUnitOfWork(self.store), self.processor, clock, ids
        )

    def _actor(self) -> Actor:
        return Actor(
            user_id=UserId(self.ids.new()),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )

    def add(self, actor: Actor, data: bytes = JPEG, label: str = "") -> PhotoData:
        return self.portal.call(self.use_cases.add_photo, actor, data, label)

    def library(self, actor: Actor) -> PhotoLibraryData:
        return self.portal.call(self.use_cases.list_photos, actor)

    def numbers(self, actor: Actor) -> list[int]:
        return [photo.photo_number for photo in self.library(actor).photos]

    def read(self, actor: Actor, number: int) -> bytes:
        return self.portal.call(self.use_cases.read_photo, actor, number)

    def delete(self, actor: Actor, number: int) -> None:
        self.portal.call(self.use_cases.delete_photo, actor, number)

    def used(self, actor: Actor, number: int, days: int) -> None:
        self.store.use(actor.user_id, number, self.clock.now() + timedelta(days=days))


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def test_a_new_user_has_no_photos_and_nothing_to_suggest(world: World) -> None:
    library = world.library(world.alice)
    assert (library.photos, library.suggested_photo_number) == ((), None)


def test_an_added_photo_is_numbered_from_one_with_its_size_and_time(
    world: World,
) -> None:
    added = world.add(world.alice, label="Office")
    assert (
        added.photo_number,
        added.label,
        added.width,
        added.height,
        added.created_at,
        added.last_used_at,
    ) == (1, "Office", 858, 960, world.clock.now(), None)


def test_the_stored_bytes_are_what_the_processor_returned(world: World) -> None:
    world.add(world.alice, b"original")
    assert world.read(world.alice, 1) == b"jpeg:original"


def test_numbers_grow_per_user(world: World) -> None:
    world.add(world.alice)
    world.add(world.alice)
    assert world.add(world.bob).photo_number == 1
    assert world.add(world.alice).photo_number == 3


def test_a_deleted_number_is_not_given_again(world: World) -> None:
    world.add(world.alice)
    world.add(world.alice)
    world.delete(world.alice, 2)
    assert world.add(world.alice).photo_number == 3


def test_an_empty_file_is_rejected_and_nothing_is_stored(world: World) -> None:
    with pytest.raises(InvalidValue) as error:
        world.add(world.alice, b"")
    assert (error.value.field, error.value.message) == (
        "file",
        "Файл порожній — вибери фото.",
    )
    assert world.numbers(world.alice) == []
    assert world.processor.calls == []


def test_a_file_over_15_mb_is_rejected_before_it_is_processed(world: World) -> None:
    with pytest.raises(InvalidValue) as error:
        world.add(world.alice, b"x" * (15 * MB + 1))
    assert (error.value.field, error.value.message) == ("file", "Фото — до 15 МБ.")
    assert world.numbers(world.alice) == []
    assert world.processor.calls == []


def test_a_file_of_exactly_15_mb_is_processed(world: World) -> None:
    world.add(world.alice, b"x" * (15 * MB))
    assert world.numbers(world.alice) == [1]


def test_a_file_that_is_not_an_image_is_rejected_and_nothing_is_stored(
    world: World,
) -> None:
    with pytest.raises(InvalidValue) as error:
        world.add(world.alice, NOT_AN_IMAGE)
    assert error.value.message == "Фото — JPEG, PNG або WebP."
    assert world.numbers(world.alice) == []


def test_a_label_becomes_one_trimmed_line(world: World) -> None:
    assert world.add(world.alice, label="  Office \n  shot\t2 ").label == (
        "Office shot 2"
    )


def test_a_label_over_100_characters_is_rejected_and_nothing_is_stored(
    world: World,
) -> None:
    with pytest.raises(InvalidValue) as error:
        world.add(world.alice, label="я" * 101)
    assert (error.value.field, error.value.message) == (
        "label",
        "Підпис фото — до 100 символів.",
    )
    assert world.numbers(world.alice) == []


def test_photos_are_listed_newest_first(world: World) -> None:
    world.add(world.alice)
    world.clock.advance(timedelta(days=1))
    world.add(world.alice)
    world.clock.advance(timedelta(days=1))
    world.add(world.alice)
    assert world.numbers(world.alice) == [3, 2, 1]


def test_without_a_used_photo_the_newest_is_suggested(world: World) -> None:
    world.add(world.alice)
    world.clock.advance(timedelta(days=1))
    world.add(world.alice)
    assert world.library(world.alice).suggested_photo_number == 2


def test_the_last_used_photo_is_suggested_over_a_newer_one(world: World) -> None:
    world.add(world.alice)
    world.clock.advance(timedelta(days=1))
    world.add(world.alice)
    world.used(world.alice, 1, days=5)
    library = world.library(world.alice)
    assert library.suggested_photo_number == 1
    assert [(p.photo_number, p.last_used_at is not None) for p in library.photos] == [
        (2, False),
        (1, True),
    ]


def test_a_user_sees_only_their_own_photos(world: World) -> None:
    world.add(world.alice, label="mine")
    assert world.numbers(world.bob) == []
    assert world.library(world.bob).suggested_photo_number is None


def test_reading_someone_elses_or_a_missing_photo_is_not_found(world: World) -> None:
    world.add(world.alice)
    assert world.read(world.alice, 1) == b"jpeg:" + JPEG[:20]
    for number in (1, 2):
        with pytest.raises(NotFound):
            world.read(world.bob, number)
    with pytest.raises(NotFound):
        world.read(world.alice, 2)


def test_deleting_removes_the_photo_and_its_bytes(world: World) -> None:
    world.add(world.alice)
    world.delete(world.alice, 1)
    assert world.numbers(world.alice) == []
    with pytest.raises(NotFound):
        world.read(world.alice, 1)


def test_deleting_someone_elses_or_a_missing_photo_is_not_found_and_changes_nothing(
    world: World,
) -> None:
    world.add(world.alice)
    for actor, number in ((world.bob, 1), (world.alice, 2)):
        with pytest.raises(NotFound):
            world.delete(actor, number)
    assert world.numbers(world.alice) == [1]
