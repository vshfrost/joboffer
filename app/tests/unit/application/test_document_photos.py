"""Фото в шапці CV: вибір у брифі, перевірка власника, рендер, «востаннє в CV», листи без фото.

Тексти помилок — як у v1 (`origin/main` `99a2007`).
"""

from datetime import timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.actor import Actor
from application.contracts.documents import CoverLetterData, CvBriefData, DocumentData
from application.contracts.photos import PhotoLibraryData
from application.documents.use_cases import DocumentUseCases
from application.photos.use_cases import PhotoUseCases
from domain.documents.lint import LintCode
from domain.shared.errors import InvalidValue
from tests.support.clock import FakeClock
from tests.support.documents import InMemoryDocumentUnitOfWork
from tests.support.ids import SequentialIds
from tests.support.photos import FakeProcessor, InMemoryPhotoUnitOfWork
from tests.support.photos import Store as PhotoStore
from tests.unit.application.test_document_use_cases import (
    FakePrompts,
    World,
    cv_data,
    letter_text,
)


class PhotoWorld(World):
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        super().__init__(portal, clock, ids)
        self.photo_store = PhotoStore()
        self.processor = FakeProcessor()
        self.photos = PhotoUseCases(
            lambda: InMemoryPhotoUnitOfWork(self.photo_store),
            self.processor,
            clock,
            ids,
        )
        self.documents = DocumentUseCases(
            lambda: InMemoryDocumentUnitOfWork(
                self.jobs_store,
                self.docs_store,
                self.facts_store,
                self.profiles,
                self.photo_store,
            ),
            clock,
            ids,
            FakePrompts(),
            self.pdf.output(),
        )

    def add_photo(self, actor: Actor, data: bytes = b"portrait") -> int:
        self.clock.advance(timedelta(minutes=1))
        added = self.portal.call(self.photos.add_photo, actor, data, "")
        return added.photo_number

    def library(self, actor: Actor) -> PhotoLibraryData:
        return self.portal.call(self.photos.list_photos, actor)

    def save_cv_with(
        self, actor: Actor, job: int, fact: int, photo: int | None
    ) -> DocumentData:
        self.clock.advance(timedelta(minutes=1))
        return self.portal.call(
            self.documents.save_cv, actor, job, cv_data(fact), photo
        )

    def brief(self, actor: Actor, job: int) -> CvBriefData:
        return self.prepare_cv(actor, job)


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> PhotoWorld:
    return PhotoWorld(portal, clock, ids)


def ready(world: PhotoWorld) -> tuple[int, int]:
    """Вакансія Аліси з текстом і підтверджений факт: (номер вакансії, номер факту)."""
    return world.seed(world.alice), world.fact(world.alice, "Python")


# --- бриф --------------------------------------------------------------------


def test_the_cv_brief_of_a_user_without_photos_offers_none(world: PhotoWorld) -> None:
    job, _ = ready(world)

    photos = world.brief(world.alice, job).photos

    assert (photos.photos, photos.suggested_photo_number) == ((), None)


def test_the_cv_brief_offers_the_users_photos_newest_first_and_suggests_the_newest(
    world: PhotoWorld,
) -> None:
    job, _ = ready(world)
    world.add_photo(world.alice)
    world.add_photo(world.alice)
    world.add_photo(world.bob)

    photos = world.brief(world.alice, job).photos

    assert [p.photo_number for p in photos.photos] == [2, 1]
    assert photos.suggested_photo_number == 2


def test_after_a_cv_with_a_photo_that_photo_is_suggested_first(
    world: PhotoWorld,
) -> None:
    job, fact = ready(world)
    world.add_photo(world.alice)
    world.add_photo(world.alice)
    world.save_cv_with(world.alice, job, fact, 1)

    photos = world.brief(world.alice, job).photos

    assert photos.suggested_photo_number == 1
    assert photos.photos[1].last_used_at == world.clock.now()


def test_the_previous_cv_in_the_brief_remembers_its_photo(world: PhotoWorld) -> None:
    job, fact = ready(world)
    world.add_photo(world.alice)
    world.save_cv_with(world.alice, job, fact, 1)

    previous = world.brief(world.alice, job).previous

    assert previous is not None
    assert previous.photo_number == 1


# --- збереження ----------------------------------------------------------------


def test_a_cv_with_the_users_photo_is_saved_with_it_and_rendered_with_its_bytes(
    world: PhotoWorld,
) -> None:
    job, fact = ready(world)
    number = world.add_photo(world.alice, b"portrait")

    saved = world.save_cv_with(world.alice, job, fact, number)

    assert saved.photo_number == number
    assert world.pdf.photos == [b"jpeg:portrait"]
    assert world.listed(world.alice, job)[0].photo_number == number


def test_a_cv_without_a_photo_is_rendered_and_saved_without_one(
    world: PhotoWorld,
) -> None:
    job, fact = ready(world)
    world.add_photo(world.alice)

    saved = world.save_cv_with(world.alice, job, fact, None)

    assert saved.photo_number is None
    assert world.pdf.photos == [None]


def test_saving_a_cv_marks_the_photo_as_used_then(world: PhotoWorld) -> None:
    job, fact = ready(world)
    world.add_photo(world.alice)
    world.add_photo(world.alice)

    world.save_cv_with(world.alice, job, fact, 1)

    used = {p.photo_number: p.last_used_at for p in world.library(world.alice).photos}
    assert used == {2: None, 1: world.clock.now()}


def test_a_cv_with_another_users_photo_is_refused_and_nothing_is_saved(
    world: PhotoWorld,
) -> None:
    job, fact = ready(world)
    theirs = world.add_photo(world.bob)

    with pytest.raises(InvalidValue) as error:
        world.save_cv_with(world.alice, job, fact, theirs)

    assert (error.value.field, error.value.message) == (
        "photo_id",
        f"Фото {theirs} не знайдено в профілі.",
    )
    assert world.listed(world.alice, job) == ()
    assert (world.pdf.rendered, world.pdf.files) == ([], {})


def test_a_cv_with_a_missing_photo_is_refused_and_nothing_is_saved(
    world: PhotoWorld,
) -> None:
    job, fact = ready(world)

    with pytest.raises(InvalidValue) as error:
        world.save_cv_with(world.alice, job, fact, 5)

    assert error.value.message == "Фото 5 не знайдено в профілі."
    assert world.listed(world.alice, job) == ()


def test_unknown_facts_are_reported_before_the_photo(world: PhotoWorld) -> None:
    job, _ = ready(world)

    with pytest.raises(InvalidValue) as error:
        world.save_cv_with(world.alice, job, 99, 5)

    assert "Фото" not in error.value.message


def test_a_cover_letter_has_no_photo(world: PhotoWorld) -> None:
    job, fact = ready(world)
    world.add_photo(world.alice)

    saved = world.save_letter(
        world.alice,
        job,
        CoverLetterData(text=letter_text(), fact_ids=(fact,)),
    )

    assert saved.photo_number is None


def test_a_job_document_listing_shows_the_photo_of_the_current_cv(
    world: PhotoWorld,
) -> None:
    job, fact = ready(world)
    world.add_photo(world.alice)
    world.save_cv_with(world.alice, job, fact, 1)
    world.save_cv_with(world.alice, job, fact, None)

    items = world.portal.call(world.documents.list_job_documents, world.alice, job)

    assert [(i.version, i.photo_number) for i in items] == [(2, None)]


def test_checking_a_cv_with_a_missing_photo_reports_it_without_rendering(
    world: PhotoWorld,
) -> None:
    job, fact = ready(world)

    checked = world.portal.call(
        world.documents.check_cv, world.alice, job, cv_data(fact), 5
    )

    assert checked.passed is False
    assert [(i.code, i.message) for i in checked.issues] == [
        (LintCode.INVALID_VALUE, "Фото 5 не знайдено в профілі.")
    ]
    assert world.pdf.rendered == []


def test_checking_a_cv_with_the_users_photo_renders_it_in_memory_and_saves_nothing(
    world: PhotoWorld,
) -> None:
    job, fact = ready(world)
    world.add_photo(world.alice, b"portrait")

    checked = world.portal.call(
        world.documents.check_cv, world.alice, job, cv_data(fact), 1
    )

    assert checked.passed is True
    assert world.pdf.photos == [b"jpeg:portrait"]
    assert world.pdf.files == {}
    assert world.listed(world.alice, job) == ()
