"""PDF версії через HTTP: `GET /documents/{document_id}/pdf` — лише власнику з чинною сесією."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.documents.document import (
    Claim,
    CoverLetter,
    Cv,
    CvEntry,
    CvSection,
    CvSectionName,
)
from domain.documents.ids import DocumentId
from domain.identity.ids import UserId
from infrastructure.db.unit_of_work import unit_of_work_factory
from infrastructure.pdf.files import FileDocuments
from tests.integration.test_jobs_http import JobsSession, alice, bob, make_client
from tests.integration.test_profile_http import SECTIONS

__all__ = ["alice", "bob", "make_client"]

NOW = datetime(2026, 3, 4, 5, 6, tzinfo=UTC)
CV = Cv(
    Claim("Senior Engineer", (1,)),
    Claim("Summary", (1,)),
    (CvSection(CvSectionName.SKILLS, (CvEntry(Claim("Python", (1,))),)),),
)
LETTER = CoverLetter(("Dear team,", " ".join(["word"] * 150), "Best, Alex"), (1,))


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBOFFER_DOCUMENTS_DIR", str(tmp_path / "documents"))


class Library:
    """Кладе документ і його PDF напряму в сховища (до HTTP версії приходять лише через MCP)."""

    def __init__(
        self, portal: BlockingPortal, engine: AsyncEngine, root: Path, email: str
    ) -> None:
        self._portal = portal
        self._engine = engine
        self._files = FileDocuments(root / "documents")
        self._email = email

    def save(
        self,
        job_number: int,
        content: Cv | CoverLetter = CV,
        pdf: bytes | None = b"%PDF-1.7 sample",
    ) -> int:
        async def run() -> int:
            async with self._engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": self._email},
                )
                user = UserId(row.scalar_one())
            async with unit_of_work_factory(self._engine)() as tx:
                job = await tx.jobs.get(user, job_number)
                assert job is not None
                document = await tx.documents.add(
                    user, DocumentId(uuid4()), job.id, content, NOW
                )
                if pdf is not None:
                    await self._files.write(document.id, pdf)
                await tx.commit()
                return document.number

        return self._portal.call(run)


@pytest.fixture
def alice_library(
    portal: BlockingPortal, engine: AsyncEngine, tmp_path: Path
) -> Library:
    return Library(portal, engine, tmp_path, "alice@example.com")


@pytest.fixture
def bob_library(portal: BlockingPortal, engine: AsyncEngine, tmp_path: Path) -> Library:
    return Library(portal, engine, tmp_path, "bob@example.com")


def name_of(session: JobsSession, full_name: str) -> None:
    body: dict[str, Any] = {**SECTIONS["contacts"], "full_name": full_name}
    assert (
        session.client.put("/profile/contacts", json=body, headers=session.csrf)
    ).status_code == 200


def pdf_of(session: JobsSession, number: object) -> Any:
    return session.client.get(f"/documents/{number}/pdf")


def test_the_pdf_requires_a_session(make_client: Any) -> None:
    response = make_client().get("/documents/1/pdf")
    assert (response.status_code, response.json()["code"]) == (401, "not_authenticated")


def test_the_owner_gets_the_pdf_inline_with_a_name_for_recruiters(
    alice: JobsSession, alice_library: Library
) -> None:
    alice.add()
    name_of(alice, "Alex Example")
    number = alice_library.save(1, CV, b"%PDF-1.7 the cv")

    response = pdf_of(alice, number)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'inline; filename="Alex_Example_CV.pdf"'
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.content == b"%PDF-1.7 the cv"


def test_a_cover_letter_has_its_own_file_name(
    alice: JobsSession, alice_library: Library
) -> None:
    alice.add()
    name_of(alice, "Alex Example")
    number = alice_library.save(1, LETTER)

    assert pdf_of(alice, number).headers["content-disposition"] == (
        'inline; filename="Alex_Example_Cover_Letter.pdf"'
    )


def test_every_version_serves_its_own_pdf(
    alice: JobsSession, alice_library: Library
) -> None:
    alice.add()
    first = alice_library.save(1, CV, b"%PDF first")
    second = alice_library.save(1, CV, b"%PDF second")

    assert (first, second) == (1, 2)
    assert pdf_of(alice, first).content == b"%PDF first"
    assert pdf_of(alice, second).content == b"%PDF second"


def test_a_profile_without_a_name_still_serves_the_pdf(
    alice: JobsSession, alice_library: Library
) -> None:
    alice.add()
    number = alice_library.save(1)

    assert pdf_of(alice, number).headers["content-disposition"] == (
        'inline; filename="CV.pdf"'
    )


def test_a_pdf_of_another_user_is_404(
    alice: JobsSession,
    bob: JobsSession,
    alice_library: Library,
) -> None:
    alice.add()
    number = alice_library.save(1)

    response = pdf_of(bob, number)

    assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_the_same_number_serves_each_user_their_own_pdf(
    alice: JobsSession,
    bob: JobsSession,
    alice_library: Library,
    bob_library: Library,
) -> None:
    alice.add(text="alice job")
    bob.add(text="bob job")
    alice_library.save(1, CV, b"%PDF alice")
    bob_library.save(1, CV, b"%PDF bob")

    assert pdf_of(alice, 1).content == b"%PDF alice"
    assert pdf_of(bob, 1).content == b"%PDF bob"


def test_a_missing_document_is_404(alice: JobsSession) -> None:
    assert pdf_of(alice, 99).status_code == 404
    assert pdf_of(alice, 10**30).status_code == 404
    assert pdf_of(alice, 0).status_code == 404


def test_a_missing_file_is_404_and_does_not_serve_another_version(
    alice: JobsSession, alice_library: Library
) -> None:
    alice.add()
    alice_library.save(1, CV, None)
    alice_library.save(1, CV, b"%PDF second")

    response = pdf_of(alice, 1)

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert pdf_of(alice, 2).content == b"%PDF second"


def test_a_number_that_is_not_an_integer_is_rejected(alice: JobsSession) -> None:
    assert pdf_of(alice, "abc").status_code == 422


def test_the_route_is_get_only(alice: JobsSession) -> None:
    assert alice.client.post("/documents/1/pdf", headers=alice.csrf).status_code == 405
