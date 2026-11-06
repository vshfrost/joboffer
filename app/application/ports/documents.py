"""Порти контексту documents: репозиторій документів і unit of work, що його відкриває.

Документ — за номером у межах користувача (`number`); вакансія — за `JobId`, який use case бере
з власної вакансії користувача, тож чужі документи недосяжні.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from application.ports.analysis import AnalysisRepository
from application.ports.facts import FactRepository
from application.ports.jobs import JobRepository
from application.ports.photos import PhotoRepository
from application.ports.profile import ProfileRepository
from application.ports.unit_of_work import UnitOfWork
from domain.documents.document import CoverLetter, Cv, Document, DocumentKind
from domain.documents.ids import DocumentId
from domain.documents.lint import LintReport, PdfLayer
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.photos.ids import PhotoId
from domain.profile.contacts import Contacts


class DocumentRepository(Protocol):
    async def add(  # noqa: PLR0913, PLR0917
        self,
        user_id: UserId,
        document_id: DocumentId,
        job_id: JobId,
        content: Cv | CoverLetter,
        now: datetime,
        number: int | None = None,
        lint: LintReport | None = None,
        photo_id: PhotoId | None = None,
    ) -> Document:
        """Зберігає нову версію: наступна для виду документа (CV чи лист) цієї вакансії, з 1.
        `number` не задано — наступний номер користувача (з 1); задано явно (перенос з v1) —
        лічильник не відстає від нього. `lint` — знімок ATS-звіту на момент збереження; `photo_id` —
        фото в шапці CV (лише для CV)."""
        ...

    async def get(self, user_id: UserId, number: int) -> Document | None:
        """Версія за номером документа; чужа й неіснуюча не відрізняються."""
        ...

    async def list_for_job(self, user_id: UserId, job_id: JobId) -> list[Document]:
        """Усі версії обох видів, новіші першими."""
        ...

    async def delete_for_job(
        self, user_id: UserId, job_id: JobId, kind: DocumentKind, keep: DocumentId
    ) -> list[DocumentId]:
        """Видаляє усі версії цього виду цієї вакансії, крім `keep`; повертає їхні id (щоб
        прибрати PDF). Одноразові посилання на PDF зникають разом із ними. Інший вид, інші
        вакансії й інші користувачі недоторкані."""
        ...

    async def superseded(self) -> list[DocumentId]:
        """Усі версії всіх користувачів, крім найновішої для кожного (користувач, вакансія, вид)."""
        ...

    async def delete(self, document_ids: Sequence[DocumentId]) -> None:
        """Видаляє документи за внутрішніми id."""
        ...


class PdfRenderer(Protocol):
    async def render_cv(
        self, cv: Cv, contacts: Contacts, photo: bytes | None = None
    ) -> bytes:
        """`photo` — JPEG для шапки або None (без фото)."""
        ...

    async def render_cover_letter(
        self, letter: CoverLetter, contacts: Contacts
    ) -> bytes: ...


class PdfInspector(Protocol):
    async def inspect(self, pdf: bytes) -> PdfLayer:
        """Що в PDF бачить парсер ATS: текстовий шар, сторінки, невбудовані шрифти."""
        ...


class DocumentFiles(Protocol):
    """PDF версій; ключ — внутрішній id документа, не дані користувача."""

    async def write(self, document_id: DocumentId, data: bytes) -> None: ...

    async def read(self, document_id: DocumentId) -> bytes | None:
        """None — файлу нема."""
        ...

    async def exists(self, document_id: DocumentId) -> bool: ...

    async def delete(self, document_id: DocumentId) -> None:
        """Прибирає файл; його відсутність — не помилка."""
        ...


@dataclass(frozen=True, slots=True)
class DocumentOutput:
    """Адаптери виходу документів, які збирає bootstrap: рендер PDF, його перевірка для
    ATS-lint і сховище файлів."""

    renderer: PdfRenderer
    inspector: PdfInspector
    files: DocumentFiles


class DocumentUnitOfWork(UnitOfWork, Protocol):
    @property
    def jobs(self) -> JobRepository: ...

    @property
    def documents(self) -> DocumentRepository: ...

    @property
    def facts(self) -> FactRepository: ...

    @property
    def photos(self) -> PhotoRepository: ...

    @property
    def analyses(self) -> AnalysisRepository: ...

    @property
    def profiles(self) -> ProfileRepository: ...
