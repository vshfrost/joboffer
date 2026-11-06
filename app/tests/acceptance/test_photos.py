"""Кроки для features/photos_*.feature і documents_photo.feature: use cases фото й документів + in-memory адаптери.

Нормалізація Pillow — адаптер, у core-наборі його нема: фейк `SizedProcessor` читає розмір кадру з префікса файлу
(«IMG 858x960 …»), а правила рамки застосовує справжній `check_frame` з домену. Усе інше — справжні use cases.
Фото — за номером на користувача (`photo_id`), документ — за номером документа; внутрішні UUID у сценаріях не фігурують.
Кроки загальні з `test_documents.py` (користувач, вакансія, факти, імʼя) оголошено знову: pytest-bdd бачить кроки
лише в модулі, де вони визначені.
"""

import re
from dataclasses import replace
from datetime import timedelta
from types import TracebackType
from typing import Self

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.documents import CoverLetterData, CvBriefData
from application.contracts.photos import PhotoData, PhotoLibraryData
from application.documents.use_cases import DocumentUseCases
from application.photos.use_cases import PhotoUseCases
from domain.documents.document import DocumentKind
from domain.identity.ids import UserId
from domain.photos.photo import NewPhoto
from domain.shared.errors import InvalidValue
from tests.acceptance.test_documents import (
    FakePrompts,
    action,
    cv_data,
    letter_text,
    numbers,
    rx,
    setup,
)
from tests.acceptance.test_documents import World as DocumentsWorld
from tests.support.clock import FakeClock
from tests.support.documents import DocumentStore, InMemoryDocumentUnitOfWork
from tests.support.ids import SequentialIds
from tests.support.photos import InMemoryPhotos
from tests.support.photos import Store as PhotoStore

scenarios(
    "features/photos_upload.feature",
    "features/photos_library.feature",
    "features/photos_users.feature",
    "features/documents_photo.feature",
)

NOT_AN_IMAGE = "Фото — JPEG, PNG або WebP."
HEADER = re.compile(rb"^IMG (\d+)x(\d+)")


class SizedProcessor:
    """Нормалізація без Pillow: розмір кадру — у префіксі файлу; решта правил — справжні."""

    def __init__(self) -> None:
        self.parsed = 0

    async def normalize(self, data: bytes) -> NewPhoto:
        self.parsed += 1
        found = HEADER.match(data)
        if found is None:
            raise InvalidValue("file", NOT_AN_IMAGE)
        width, height = int(found.group(1)), int(found.group(2))
        # `NewPhoto` сам перевіряє рамку (`check_frame`) — як це робить адаптер Pillow.
        return NewPhoto(
            data=f"jpeg:{width}x{height}".encode(), width=width, height=height
        )


class DetachingPhotos(InMemoryPhotos):
    """Видалення фото, як FK `ON DELETE SET NULL` у Postgres: документи лишаються, але без фото."""

    def __init__(self, store: PhotoStore, documents: DocumentStore) -> None:
        super().__init__(store)
        self._documents = documents

    async def delete(self, user_id: UserId, number: int) -> bool:
        deleted = await super().delete(user_id, number)
        if deleted:
            for key, document in list(self._documents.documents.items()):
                if key[0] == user_id and document.photo_number == number:
                    self._documents.documents[key] = replace(
                        document, photo_number=None
                    )
        return deleted


class PhotoUnitOfWork:
    """Транзакція фото на тих самих сховищах, що й документи: видалення бачить документи."""

    def __init__(self, photos: PhotoStore, documents: DocumentStore) -> None:
        self._store = photos
        self._documents = documents
        self._staged: PhotoStore | None = None

    @property
    def photos(self) -> DetachingPhotos:
        assert self._staged is not None, "UnitOfWork поза `async with`"
        return DetachingPhotos(self._staged, self._documents)

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
        assert self._staged is not None, "UnitOfWork поза `async with`"
        self._store.photos = self._staged.photos
        self._store.data = self._staged.data
        self._store.counters = self._staged.counters
        self._store.ids = self._staged.ids


def image(width: str, height: str, size: int | None = None) -> bytes:
    """Файл-«картинка» кадру `width` × `height`, за потреби добитий пробілами до `size` байтів."""
    data = f"IMG {width}x{height}".encode()
    return data if size is None else (data + b" " * size)[:size]


class World(DocumentsWorld):
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        super().__init__(portal, clock, ids)
        self.photo_store = PhotoStore()
        self.processor = SizedProcessor()
        self.photos = PhotoUseCases(
            lambda: PhotoUnitOfWork(self.photo_store, self.docs_store),
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
        self.added: PhotoData | None = None
        self.library: PhotoLibraryData | None = None
        self.read: bytes | None = None

    def reset_outcome(self) -> None:
        super().reset_outcome()
        self.added = None
        self.library = None
        self.read = None

    def add_photo(self, data: bytes, label: str = "") -> None:
        self.clock.advance(timedelta(minutes=1))
        self.added = self.attempt(
            lambda: self.photos.add_photo(self.actor, data, label)
        )

    def save_cv_with_photo(self, job: int, facts: str, photo: int | None) -> None:
        self.clock.advance(timedelta(minutes=1))
        data = cv_data(numbers(facts))
        self.saved = self.attempt(
            lambda: self.documents.save_cv(self.actor, job, data, photo)
        )


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


# --- хто я, вакансії, факти -----------------------------------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_given(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@setup(r'^є вакансія "(?P<title>[^"]*)" з текстом "(?P<text>[^"]*)"$')
def job_with_text(world: World, title: str, text: str) -> None:
    world.add_job(title, text)


@setup(
    r'^у мене є (?P<state>підтверджений|непідтверджений) факт (?P<kind>\w+) "(?P<text>[^"]*)"$'
)
def fact(world: World, state: str, kind: str, text: str) -> None:
    world.add_fact(kind, text, confirmed=state == "підтверджений")


@action(r'^я (?:задаю|задав) ім\'я "(?P<value>[^"]*)"$')
def set_name(world: World, value: str) -> None:
    world.set_contacts(full_name=value)


# --- додавання фото ---------------------------------------------------------------------------


@action(r"^я (?:додаю|додав) фото (?P<w>\d+) × (?P<h>\d+)$")
def add_photo(world: World, w: str, h: str) -> None:
    world.add_photo(image(w, h))


@action(
    r'^я (?:додаю|додав) фото (?P<w>\d+) × (?P<h>\d+) з підписом "(?P<label>[^"]*)"$'
)
def add_photo_labelled(world: World, w: str, h: str, label: str) -> None:
    world.add_photo(image(w, h), label)


@bdd_when(
    rx(
        r"^я додаю фото (?P<w>\d+) × (?P<h>\d+) з підписом із (?P<length>\d+) символ\w*$"
    )
)
def add_photo_long_label(world: World, w: str, h: str, length: str) -> None:
    world.add_photo(image(w, h), "я" * int(length))


@bdd_when(
    rx(r"^я додаю фото (?P<w>\d+) × (?P<h>\d+) розміром файлу (?P<size>\d+) байт\w*$")
)
def add_photo_sized(world: World, w: str, h: str, size: str) -> None:
    world.add_photo(image(w, h, int(size)))


@bdd_when(rx(r"^я додаю порожній файл$"))
def add_empty(world: World) -> None:
    world.add_photo(b"")


@bdd_when(rx(r'^я додаю файл "(?P<name>[^"]*)", що не є картинкою$'))
def add_text_file(world: World, name: str) -> None:
    world.add_photo(f"це текст, а не {name}".encode())


@bdd_given(rx(r"^я додаю фото (?P<w>\d+) × (?P<h>\d+), але отримую помилку$"))
def add_rejected(world: World, w: str, h: str) -> None:
    world.add_photo(image(w, h))
    assert world.error is not None, "фото мало бути відхилене"


# --- галерея, читання, видалення ---------------------------------------------------------------


@bdd_when(rx(r"^я переглядаю свої фото$"))
def list_photos(world: World) -> None:
    world.library = world.attempt(lambda: world.photos.list_photos(world.actor))


@bdd_when(rx(r"^я читаю фото (?P<number>\d+)$"))
def read_photo(world: World, number: str) -> None:
    world.read = world.attempt(
        lambda: world.photos.read_photo(world.actor, int(number))
    )


@action(r"^я (?:видаляю|видалив) фото (?P<number>\d+)$")
def delete_photo(world: World, number: str) -> None:
    world.attempt(lambda: world.photos.delete_photo(world.actor, int(number)))


def library_of(world: World) -> PhotoLibraryData:
    """Галерея поточного користувача: або щойно переглянута, або запитана тут."""
    if world.library is None:
        world.library = world.portal.call(world.photos.list_photos, world.actor)
    return world.library


@bdd_then(rx(r"^збережено фото (?P<number>\d+) розміром (?P<w>\d+) × (?P<h>\d+)$"))
def photo_saved(world: World, number: str, w: str, h: str) -> None:
    assert world.error is None, world.error
    assert world.added is not None, "фото не збережено"
    assert (world.added.photo_number, world.added.width, world.added.height) == (
        int(number),
        int(w),
        int(h),
    )


@bdd_then(rx(r'^збережено фото (?P<number>\d+) з підписом "(?P<label>[^"]*)"$'))
def photo_label(world: World, number: str, label: str) -> None:
    assert world.error is None, world.error
    assert world.added is not None, "фото не збережено"
    assert (world.added.photo_number, world.added.label) == (int(number), label)


@bdd_then("у галереї нема фото")
def gallery_empty(world: World) -> None:
    assert library_of(world).photos == ()


@bdd_then(rx(r"^у галереї (?P<count>\d+) фото$"))
def gallery_count(world: World, count: str) -> None:
    assert len(library_of(world).photos) == int(count)


@bdd_then(rx(r'^фото в галереї за порядком: "(?P<labels>[^"]*)"$'))
def gallery_order(world: World, labels: str) -> None:
    assert world.error is None, world.error
    found = [photo.label for photo in library_of(world).photos]
    assert found == [part.strip() for part in labels.split(";")]


@bdd_then(rx(r"^пропонується фото (?P<number>\d+)$"))
def suggested(world: World, number: str) -> None:
    assert library_of(world).suggested_photo_number == int(number)


@bdd_then("нічого не пропонується")
def nothing_suggested(world: World) -> None:
    assert library_of(world).suggested_photo_number is None


def photo_in_gallery(world: World, number: str) -> PhotoData:
    return next(
        photo for photo in library_of(world).photos if photo.photo_number == int(number)
    )


@bdd_then(rx(r"^фото (?P<number>\d+) ще не використовувалось$"))
def photo_unused(world: World, number: str) -> None:
    assert photo_in_gallery(world, number).last_used_at is None


@bdd_then(rx(r"^фото (?P<number>\d+) використано в CV$"))
def photo_used(world: World, number: str) -> None:
    assert photo_in_gallery(world, number).last_used_at is not None


@bdd_then(rx(r"^прочитано кадр (?P<w>\d+) × (?P<h>\d+)$"))
def read_frame(world: World, w: str, h: str) -> None:
    assert world.error is None, world.error
    assert world.read == f"jpeg:{w}x{h}".encode()


@bdd_then("файл не розбирався")
def not_parsed(world: World) -> None:
    assert world.processor.parsed == 0


# --- CV з фото ---------------------------------------------------------------------------------


@action(
    r'^я (?:зберігаю|зберіг) CV для вакансії (?P<job>\d+) на фактах "(?P<facts>[^"]*)" з фото (?P<photo>\d+)$'
)
def save_cv_photo(world: World, job: str, facts: str, photo: str) -> None:
    world.save_cv_with_photo(int(job), facts, int(photo))


@action(
    r'^я (?:зберігаю|зберіг) CV для вакансії (?P<job>\d+) на фактах "(?P<facts>[^"]*)" без фото$'
)
def save_cv_no_photo(world: World, job: str, facts: str) -> None:
    world.save_cv_with_photo(int(job), facts, None)


@bdd_when(
    rx(
        r"^я зберігаю лист для вакансії (?P<job>\d+) із (?P<count>\d+) слів на фактах \"(?P<facts>[^\"]*)\"$"
    )
)
def save_letter(world: World, job: str, count: str, facts: str) -> None:
    world.clock.advance(timedelta(minutes=1))
    data = CoverLetterData(text=letter_text(int(count)), fact_ids=numbers(facts))
    world.saved = world.attempt(
        lambda: world.documents.save_cover_letter(world.actor, int(job), data)
    )


@bdd_when(rx(r"^я готую бриф CV для вакансії (?P<job>\d+)$"))
def prepare_cv(world: World, job: str) -> None:
    world.cv_brief = world.attempt(
        lambda: world.documents.prepare_cv(world.actor, int(job))
    )


def brief_of(world: World) -> CvBriefData:
    assert world.error is None, world.error
    assert world.cv_brief is not None, "бриф не готували"
    return world.cv_brief


@bdd_then("у брифі CV фото нема")
def brief_no_photos(world: World) -> None:
    assert brief_of(world).photos.photos == ()


@bdd_then(rx(r'^у брифі CV фото за порядком: "(?P<labels>[^"]*)"$'))
def brief_photos(world: World, labels: str) -> None:
    found = [photo.label for photo in brief_of(world).photos.photos]
    assert found == [part.strip() for part in labels.split(";")]


@bdd_then(rx(r"^у брифі CV пропонується фото (?P<number>\d+)$"))
def brief_suggested(world: World, number: str) -> None:
    assert brief_of(world).photos.suggested_photo_number == int(number)


@bdd_then("у брифі CV нічого не пропонується")
def brief_nothing_suggested(world: World) -> None:
    assert brief_of(world).photos.suggested_photo_number is None


@bdd_then(rx(r"^попередня версія в брифі має фото (?P<number>\d+)$"))
def brief_previous_photo(world: World, number: str) -> None:
    previous = brief_of(world).previous
    assert previous is not None
    assert previous.photo_number == int(number)


@bdd_then(
    rx(
        r"^збережено документ (?P<number>\d+): вид \"(?P<kind>cv|cl)\", версія (?P<version>\d+), вакансія (?P<job>\d+)$"
    )
)
def saved_document(
    world: World, number: str, kind: str, version: str, job: str
) -> None:
    assert world.error is None, world.error
    saved = world.saved
    assert saved is not None, "нічого не збережено"
    expected = DocumentKind.CV if kind == "cv" else DocumentKind.COVER_LETTER
    assert (saved.document_number, saved.kind, saved.version, saved.job_number) == (
        int(number),
        expected,
        int(version),
        int(job),
    )


@bdd_then(rx(r"^збережений документ має фото (?P<number>\d+)$"))
def saved_has_photo(world: World, number: str) -> None:
    assert world.error is None, world.error
    assert world.saved is not None
    assert world.saved.photo_number == int(number)


@bdd_then("збережений документ без фото")
def saved_without_photo(world: World) -> None:
    assert world.error is None, world.error
    assert world.saved is not None
    assert world.saved.photo_number is None


def rendered_photo_bytes(world: World, number: int) -> bytes:
    stored = world.photo_store.data[(world.actor.user_id, number)]
    return stored


@bdd_then(rx(r"^PDF відрендерено з фото (?P<number>\d+)$"))
def pdf_with_photo(world: World, number: str) -> None:
    assert world.pdf.photos, "рендеру не було"
    assert world.pdf.photos[-1] == rendered_photo_bytes(world, int(number))


@bdd_then("PDF відрендерено без фото")
def pdf_without_photo(world: World) -> None:
    assert world.pdf.photos, "рендеру не було"
    assert world.pdf.photos[-1] is None


@bdd_then(rx(r"^нічого не збережено для вакансії (?P<job>\d+)$"))
def nothing_saved(world: World, job: str) -> None:
    assert world.documents_of(int(job)) == ()
    assert world.pdf.files == {}
    assert world.pdf.rendered == []


# --- список документів і PDF ------------------------------------------------------------------


@bdd_when(rx(r"^я переглядаю документи вакансії (?P<job>\d+)$"))
def list_documents(world: World, job: str) -> None:
    world.listed = world.attempt(
        lambda: world.documents.list_documents(world.actor, int(job))
    )


@bdd_when(rx(r"^я переглядаю документи вакансії (?P<job>\d+) для вебу$"))
def web_list(world: World, job: str) -> None:
    world.web_list = world.attempt(
        lambda: world.documents.list_job_documents(world.actor, int(job))
    )


@bdd_when(rx(r"^я відкриваю PDF документа (?P<number>\d+)$"))
def open_pdf(world: World, number: str) -> None:
    world.pdf_file = world.attempt(
        lambda: world.documents.get_pdf(world.actor, int(number))
    )


def listed_document(world: World, number: str) -> int | None:
    assert world.error is None, world.error
    assert world.listed is not None, "список не запитували"
    item = next(i for i in world.listed if i.document_number == int(number))
    return item.photo_number


@bdd_then(rx(r"^документ (?P<number>\d+) у списку має фото (?P<photo>\d+)$"))
def listed_has_photo(world: World, number: str, photo: str) -> None:
    assert listed_document(world, number) == int(photo)


@bdd_then(rx(r"^документ (?P<number>\d+) у списку без фото$"))
def listed_without_photo(world: World, number: str) -> None:
    assert listed_document(world, number) is None


@bdd_then(rx(r"^у списку документів (?P<count>\d+) версі\w+$"))
def listed_count(world: World, count: str) -> None:
    assert world.listed is not None
    assert len(world.listed) == int(count)


def web_item(world: World, version: str) -> int | None:
    assert world.error is None, world.error
    assert world.web_list is not None, "веб-список не запитували"
    item = next(i for i in world.web_list if i.version == int(version))
    return item.photo_number


@bdd_then(rx(r"^для вебу версія (?P<version>\d+) має фото (?P<photo>\d+)$"))
def web_has_photo(world: World, version: str, photo: str) -> None:
    assert web_item(world, version) == int(photo)


@bdd_then(rx(r"^для вебу версія (?P<version>\d+) без фото$"))
def web_without_photo(world: World, version: str) -> None:
    assert web_item(world, version) is None


@bdd_then(rx(r"^для вебу файл версії (?P<number>\d+) (?P<state>є|зник)$"))
def web_file(world: World, number: str, state: str) -> None:
    assert world.web_list is not None
    item = next(i for i in world.web_list if i.document_number == int(number))
    assert item.pdf_available is (state == "є")


@bdd_then(rx(r'^PDF відкрито з назвою файлу "(?P<name>[^"]*)"$'))
def pdf_opened(world: World, name: str) -> None:
    assert world.error is None, world.error
    assert world.pdf_file is not None
    assert world.pdf_file.file_name == name


# --- помилки -----------------------------------------------------------------------------------


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def error_message(world: World, code: str, message: str) -> None:
    assert world.error is not None, "помилки не було"
    assert (world.error.code, world.error.message) == (code, message)


@bdd_then("помилки не було")
def no_error(world: World) -> None:
    assert world.error is None, world.error
