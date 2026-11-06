"""In-memory адаптер documents для core-тестів: та сама семантика, що в Postgres (номери, версії, commit).

Ділить `Store` із фейком вакансій (документ стоїть на вакансії) і сховище фактів.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Self

from domain.documents.document import CoverLetter, Cv, Document, DocumentKind
from domain.documents.ids import DocumentId
from domain.documents.lint import LintReport
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.photos.ids import PhotoId
from domain.profile.profile import Profile
from tests.support.analysis import InMemoryAnalyses
from tests.support.facts import InMemoryFacts
from tests.support.facts import Store as FactStore
from tests.support.jobs import InMemoryJobs, Store
from tests.support.photos import InMemoryPhotos
from tests.support.photos import Store as PhotoStore
from tests.support.profile import InMemoryProfiles


@dataclass
class DocumentStore:
    documents: dict[tuple[UserId, int], Document]
    counters: dict[UserId, int]

    @classmethod
    def empty(cls) -> Self:
        return cls({}, {})

    def copy(self) -> Self:
        return type(self)(dict(self.documents), dict(self.counters))


def _kind(content: Cv | CoverLetter) -> DocumentKind:
    return DocumentKind.CV if isinstance(content, Cv) else DocumentKind.COVER_LETTER


class InMemoryDocuments:
    def __init__(
        self, jobs: Store, store: DocumentStore, photos: PhotoStore | None = None
    ) -> None:
        self._jobs = jobs
        self._s = store
        self._photos = photos

    def _job_number(self, user_id: UserId, job_id: JobId) -> int:
        for (owner, number), job in self._jobs.jobs.items():
            if owner == user_id and job.id == job_id:
                return number
        raise AssertionError("документ на чужій чи неіснуючій вакансії")

    async def add(
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
        counter = self._s.counters.get(user_id, 0)
        given = counter + 1 if number is None else number
        self._s.counters[user_id] = max(counter, given)
        job_number = self._job_number(user_id, job_id)
        kind = _kind(content)
        version = 1 + max(
            (
                document.version
                for (owner, _), document in self._s.documents.items()
                if owner == user_id
                and document.job_number == job_number
                and document.kind is kind
            ),
            default=0,
        )
        photo_number = None
        if photo_id is not None:
            assert self._photos is not None
            owner, photo_number = self._photos.owner_of(photo_id)
            assert owner == user_id
            self._photos.use(user_id, photo_number, now)
        added = Document(
            document_id,
            given,
            job_number,
            kind,
            version,
            content,
            now,
            lint,
            photo_number,
        )
        self._s.documents[(user_id, given)] = added
        return added

    async def get(self, user_id: UserId, number: int) -> Document | None:
        return self._s.documents.get((user_id, number))

    async def list_for_job(self, user_id: UserId, job_id: JobId) -> list[Document]:
        job_number = self._job_number(user_id, job_id)
        mine = [
            document
            for (owner, _), document in self._s.documents.items()
            if owner == user_id and document.job_number == job_number
        ]
        return sorted(mine, key=lambda document: document.number, reverse=True)

    async def delete_for_job(
        self, user_id: UserId, job_id: JobId, kind: DocumentKind, keep: DocumentId
    ) -> list[DocumentId]:
        job_number = self._job_number(user_id, job_id)
        gone = [
            (key, document.id)
            for key, document in self._s.documents.items()
            if key[0] == user_id
            and document.job_number == job_number
            and document.kind is kind
            and document.id != keep
        ]
        for key, _ in gone:
            del self._s.documents[key]
        return [document_id for _, document_id in gone]

    async def superseded(self) -> list[DocumentId]:
        newest: dict[tuple[UserId, int, DocumentKind], Document] = {}
        for (owner, _), document in self._s.documents.items():
            group = (owner, document.job_number, document.kind)
            if group not in newest or newest[group].version < document.version:
                newest[group] = document
        return [
            document.id
            for document in self._s.documents.values()
            if all(document is not kept for kept in newest.values())
        ]

    async def delete(self, document_ids: Sequence[DocumentId]) -> None:
        doomed = set(document_ids)
        self._s.documents = {
            key: document
            for key, document in self._s.documents.items()
            if document.id not in doomed
        }


class InMemoryDocumentUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(
        self,
        jobs: Store,
        documents: DocumentStore,
        facts: FactStore,
        profiles: dict[UserId, Profile],
        photos: PhotoStore | None = None,
    ) -> None:
        self._photos = photos if photos is not None else PhotoStore()
        self._staged_photos: PhotoStore | None = None
        self._jobs = jobs
        self._documents = documents
        self._facts = facts
        self._profiles = profiles
        self._staged_jobs: Store | None = None
        self._staged: DocumentStore | None = None

    def _open(self) -> tuple[Store, DocumentStore]:
        if self._staged_jobs is None or self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged_jobs, self._staged

    def _open_photos(self) -> PhotoStore:
        if self._staged_photos is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged_photos

    @property
    def jobs(self) -> InMemoryJobs:
        return InMemoryJobs(self._open()[0])

    @property
    def documents(self) -> InMemoryDocuments:
        jobs, documents = self._open()
        return InMemoryDocuments(jobs, documents, self._open_photos())

    @property
    def photos(self) -> InMemoryPhotos:
        return InMemoryPhotos(self._open_photos())

    @property
    def analyses(self) -> InMemoryAnalyses:
        return InMemoryAnalyses(self._open()[0])

    @property
    def facts(self) -> InMemoryFacts:
        return InMemoryFacts(self._facts)

    @property
    def profiles(self) -> InMemoryProfiles:
        return InMemoryProfiles(self._profiles, {})

    async def __aenter__(self) -> Self:
        self._staged_jobs = self._jobs.copy()
        self._staged = self._documents.copy()
        self._staged_photos = self._photos.copy()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged_jobs = self._staged = self._staged_photos = None

    async def commit(self) -> None:
        _, documents = self._open()
        self._documents.documents = documents.documents
        self._documents.counters = documents.counters
        self._photos.photos = self._open_photos().photos
