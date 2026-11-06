"""Одноразові посилання на PDF на справжньому Postgres: у базі лише дайджест токена, посилання
спрацьовує один раз (навіть при паралельних запитах) і лише до закінчення 10 хвилин."""

import asyncio
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.documents import PdfFileData
from application.documents.downloads import DocumentDownloads
from domain.documents.document import Claim, Cv, CvEntry, CvSection, CvSectionName
from domain.documents.ids import DocumentId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.profile.contacts import Contacts
from domain.shared.errors import NotFound
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from infrastructure.pdf.files import FileDocuments
from infrastructure.system import RandomTokens
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, posting, uow
from tests.support.clock import FakeClock

__all__ = ["uow"]

CV = Cv(
    Claim("Senior Engineer", (1,)),
    Claim("Summary", (1,)),
    (CvSection(CvSectionName.SKILLS, (CvEntry(Claim("Python", (1,))),)),),
)


def actor(user: UserId) -> Actor:
    return Actor(
        user_id=user,
        channel=Channel.WEB,
        client_id="web",
        grant_id=None,
        scopes=frozenset(Scope),
        correlation_id="test",
    )


class Shelf:
    """Postgres + файли на диску + use case посилань із фейковим годинником."""

    def __init__(
        self,
        portal: BlockingPortal,
        engine: AsyncEngine,
        uow: UnitOfWorkFactory,
        root: Path,
    ) -> None:
        self.portal = portal
        self.engine = engine
        self.clock = FakeClock(NOW)
        self._uow = uow
        self._files = FileDocuments(root)
        self.downloads = DocumentDownloads(uow, self.clock, RandomTokens(), self._files)

    def save(self, user: UserId, pdf: bytes | None = b"%PDF-1.7 the cv") -> int:
        async def run() -> int:
            async with self._uow() as tx:
                await tx.profiles.save_section(
                    user, Contacts(full_name="Alex Example"), NOW
                )
                job_id = JobId(UUID(int=0xE000 + user.value.int % 100))
                await tx.jobs.add(user, job_id, posting(), NOW)
                document = await tx.documents.add(
                    user, DocumentId(UUID(int=0xF000 + user.value.int)), job_id, CV, NOW
                )
                if pdf is not None:
                    await self._files.write(document.id, pdf)
                await tx.commit()
                return document.number

        return self.portal.call(run)

    def link(self, user: UserId, number: int) -> str:
        return self.portal.call(self.downloads.create_link, actor(user), number).token

    def redeem(self, token: str) -> PdfFileData:
        return self.portal.call(self.downloads.redeem, token)

    def rows(self) -> list[dict[str, object]]:
        async def run() -> list[dict[str, object]]:
            async with self.engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT * FROM document_download_links")
                )
                return [dict(row._mapping) for row in result]

        return self.portal.call(run)


@pytest.fixture
def shelf(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory, tmp_path: Path
) -> Shelf:
    return Shelf(portal, engine, uow, tmp_path / "documents")


def test_a_link_gives_the_pdf_once(shelf: Shelf) -> None:
    token = shelf.link(ALICE, shelf.save(ALICE))

    assert shelf.redeem(token) == PdfFileData(
        data=b"%PDF-1.7 the cv", file_name="Alex_Example_CV.pdf"
    )
    with pytest.raises(NotFound):
        shelf.redeem(token)


def test_two_parallel_requests_with_the_same_link_get_the_pdf_only_once(
    shelf: Shelf,
) -> None:
    token = shelf.link(ALICE, shelf.save(ALICE))

    async def both() -> tuple[object, ...]:
        return await asyncio.gather(
            shelf.downloads.redeem(token),
            shelf.downloads.redeem(token),
            return_exceptions=True,
        )

    outcomes = shelf.portal.call(both)

    assert sorted(type(o).__name__ for o in outcomes) == ["NotFound", "PdfFileData"]


def test_the_link_dies_after_ten_minutes(shelf: Shelf) -> None:
    token = shelf.link(ALICE, shelf.save(ALICE))
    shelf.clock.advance(timedelta(minutes=10))

    with pytest.raises(NotFound):
        shelf.redeem(token)


def test_the_link_lives_until_just_before_ten_minutes(shelf: Shelf) -> None:
    token = shelf.link(ALICE, shelf.save(ALICE))
    shelf.clock.advance(timedelta(minutes=9, seconds=59))

    assert shelf.redeem(token).data == b"%PDF-1.7 the cv"


def test_the_database_holds_the_hash_of_the_token_and_never_the_token(
    shelf: Shelf,
) -> None:
    token = shelf.link(ALICE, shelf.save(ALICE))

    (row,) = shelf.rows()

    assert row["token_digest"] == hashlib.sha256(token.encode()).hexdigest()
    assert row["user_id"] == ALICE.value
    assert row["expires_at"] == NOW + timedelta(minutes=10)
    assert row["used_at"] is None
    assert token not in " ".join(str(value) for value in row.values())


def test_using_the_link_records_when(shelf: Shelf) -> None:
    token = shelf.link(ALICE, shelf.save(ALICE))
    shelf.clock.advance(timedelta(minutes=3))

    shelf.redeem(token)

    (row,) = shelf.rows()
    used: datetime = row["used_at"]  # type: ignore[assignment]
    assert used == NOW + timedelta(minutes=3)


def test_a_link_for_a_document_of_another_user_is_not_created(shelf: Shelf) -> None:
    theirs = shelf.save(BOB)

    with pytest.raises(NotFound):
        shelf.link(ALICE, theirs)

    assert shelf.rows() == []


def test_a_link_for_a_missing_document_is_not_created(shelf: Shelf) -> None:
    with pytest.raises(NotFound):
        shelf.link(ALICE, 9)

    assert shelf.rows() == []


def test_a_link_whose_pdf_file_is_gone_is_not_valid(shelf: Shelf) -> None:
    token = shelf.link(ALICE, shelf.save(ALICE, None))

    with pytest.raises(NotFound):
        shelf.redeem(token)


def test_deleting_the_document_removes_its_links(
    shelf: Shelf, portal: BlockingPortal, engine: AsyncEngine
) -> None:
    shelf.link(ALICE, shelf.save(ALICE))

    async def delete() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM documents"))

    portal.call(delete)

    assert shelf.rows() == []
