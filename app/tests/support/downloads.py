"""In-memory адаптер одноразових посилань на PDF і готовий «світ» для тестів: користувачі з
документами, годинник, детерміновані токени, фейкове сховище файлів.

Семантика посилань — та сама, що в Postgres: зберігається лише дайджест, `redeem` атомарно
використовує посилання один раз до `expires_at`, а зміни видно після `commit()`.
"""

from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID

from application.contracts.actor import Actor, Channel, Scope
from application.documents.downloads import DocumentDownloads
from domain.documents.document import (
    Claim,
    CoverLetter,
    Cv,
    CvEntry,
    CvSection,
    CvSectionName,
    Document,
    DocumentKind,
)
from domain.documents.download import DownloadGrant
from domain.documents.ids import DocumentId
from domain.identity.ids import UserId
from domain.identity.session import TokenDigest
from domain.profile.contacts import Contacts
from domain.profile.profile import Profile
from tests.support.clock import FakeClock
from tests.support.documents import (
    DocumentStore,
    InMemoryDocuments,
    InMemoryDocumentUnitOfWork,
)
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import Store as JobStore
from tests.support.pdf import Shop
from tests.support.profile import InMemoryProfiles

CV = Cv(
    Claim("Senior Engineer", (1,)),
    Claim("Summary", (1,)),
    (CvSection(CvSectionName.SKILLS, (CvEntry(Claim("Python", (1,))),)),),
)
LETTER = CoverLetter(("Dear team,", " ".join(["word"] * 150), "Best, Alex"), (1,))


@dataclass
class Link:
    user_id: UserId
    document_id: DocumentId
    expires_at: datetime
    used_at: datetime | None = None


@dataclass
class DownloadStore:
    links: dict[TokenDigest, Link] = field(default_factory=dict)

    def copy(self) -> Self:
        return type(self)({d: Link(**vars(link)) for d, link in self.links.items()})


class InMemoryDownloadLinks:
    def __init__(self, store: DownloadStore, documents: DocumentStore) -> None:
        self._s = store
        self._documents = documents

    async def add(
        self,
        user_id: UserId,
        document_id: DocumentId,
        digest: TokenDigest,
        expires_at: datetime,
    ) -> None:
        self._s.links[digest] = Link(user_id, document_id, expires_at)

    async def redeem(self, digest: TokenDigest, now: datetime) -> DownloadGrant | None:
        link = self._s.links.get(digest)
        if link is None or link.used_at is not None or now >= link.expires_at:
            return None
        link.used_at = now
        number = next(
            document.number
            for (owner, _), document in self._documents.documents.items()
            if owner == link.user_id and document.id == link.document_id
        )
        return DownloadGrant(link.user_id, number)


class InMemoryDownloadUnitOfWork:
    """Документи й профілі — з in-memory документів; зміни посилань видно лише після `commit()`."""

    def __init__(
        self,
        documents: InMemoryDocumentUnitOfWork,
        document_store: DocumentStore,
        links: DownloadStore,
    ) -> None:
        self._documents = documents
        self._document_store = document_store
        self._links = links
        self._staged: DownloadStore | None = None

    @property
    def documents(self) -> InMemoryDocuments:
        return self._documents.documents

    @property
    def profiles(self) -> InMemoryProfiles:
        return self._documents.profiles

    @property
    def download_links(self) -> InMemoryDownloadLinks:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemoryDownloadLinks(self._staged, self._document_store)

    async def __aenter__(self) -> Self:
        await self._documents.__aenter__()
        self._staged = self._links.copy()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None
        await self._documents.__aexit__(exc_type, exc, traceback)

    async def commit(self) -> None:
        assert self._staged is not None
        await self._documents.commit()
        self._links.links = self._staged.links


class SequentialTokens:
    """Детерміновані «випадкові» токени: token-1, token-2, …"""

    def __init__(self) -> None:
        self._next = 1

    def new(self) -> str:
        token = f"token-{self._next}"
        self._next += 1
        return token


class Library:
    """Користувачі з документами й PDF у фейковому сховищі, і use case посилань над ними."""

    def __init__(self, clock: FakeClock | None = None) -> None:
        self.clock = clock or FakeClock()
        self.ids = SequentialIds()
        self.tokens = SequentialTokens()
        self.shop = Shop()
        self.links = DownloadStore()
        self.documents = DocumentStore.empty()
        self.profiles: dict[UserId, Profile] = {}
        self._jobs = JobStore.empty()
        self._facts = FactStore.empty()
        self.downloads = DocumentDownloads(
            lambda: InMemoryDownloadUnitOfWork(
                InMemoryDocumentUnitOfWork(
                    self._jobs, self.documents, self._facts, self.profiles
                ),
                self.documents,
                self.links,
            ),
            self.clock,
            self.tokens,
            self.shop.output().files,
        )

    def user(self, full_name: str) -> Actor:
        user_id = UserId(self.ids.new())
        self.profiles[user_id] = Profile(contacts=Contacts(full_name=full_name))
        return Actor(
            user_id=user_id,
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )

    async def save(
        self, actor: Actor, content: Cv | CoverLetter = CV, pdf: bytes | None = b"%PDF"
    ) -> int:
        """Кладе документ користувача (і його PDF, якщо `pdf` не None) напряму в сховища."""
        number = 1 + max(
            (n for (owner, n) in self.documents.documents if owner == actor.user_id),
            default=0,
        )
        kind = DocumentKind.CV if isinstance(content, Cv) else DocumentKind.COVER_LETTER
        document = Document(
            DocumentId(UUID(int=1000 + len(self.documents.documents))),
            number,
            1,
            kind,
            1,
            content,
            self.clock.now(),
        )
        self.documents.documents[(actor.user_id, number)] = document
        if pdf is not None:
            await self.shop.output().files.write(document.id, pdf)
        return number
