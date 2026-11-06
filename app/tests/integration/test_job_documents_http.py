"""Версії документів вакансії через HTTP: `GET /jobs/{job_id}/documents` — лише власнику, без вмісту."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.documents.document import CoverLetter, Cv
from domain.documents.ids import DocumentId
from domain.documents.lint import KeywordCoverage, LintCode, LintIssue, LintReport
from domain.identity.ids import UserId
from infrastructure.db.unit_of_work import unit_of_work_factory
from infrastructure.pdf.files import FileDocuments
from tests.integration.test_documents_http import CV, LETTER, name_of
from tests.integration.test_jobs_http import JobsSession, alice, bob, make_client
from tests.support.images import HALF_FRAME, jpeg

__all__ = ["alice", "bob", "make_client"]

SAVED = datetime(2026, 3, 4, 5, 6, tzinfo=UTC)
REPORT = LintReport(
    pages=3,
    issues=(LintIssue(LintCode.PAGES, "3 сторінок, а можна до 2 — скороти."),),
    keywords=KeywordCoverage(("Python",), ("Kafka", "Go")),
)


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBOFFER_DOCUMENTS_DIR", str(tmp_path / "documents"))


class Shelf:
    """Кладе версії напряму в сховища: документи, звіти й файли."""

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
        lint: LintReport | None = REPORT,
        *,
        pdf: bool = True,
        when: datetime = SAVED,
        photo_number: int | None = None,
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
                photo = (
                    None
                    if photo_number is None
                    else await tx.photos.get(user, photo_number)
                )
                document = await tx.documents.add(
                    user,
                    DocumentId(uuid4()),
                    job.id,
                    content,
                    when,
                    lint=lint,
                    photo_id=None if photo is None else photo.id,
                )
                if pdf:
                    await self._files.write(document.id, b"%PDF-1.7")
                await tx.commit()
                return document.number

        return self._portal.call(run)


@pytest.fixture
def alice_shelf(portal: BlockingPortal, engine: AsyncEngine, tmp_path: Path) -> Shelf:
    return Shelf(portal, engine, tmp_path, "alice@example.com")


@pytest.fixture
def bob_shelf(portal: BlockingPortal, engine: AsyncEngine, tmp_path: Path) -> Shelf:
    return Shelf(portal, engine, tmp_path, "bob@example.com")


def documents_of(session: JobsSession, job: object) -> Any:
    return session.client.get(f"/jobs/{job}/documents")


def test_the_list_requires_a_session(make_client: Any) -> None:
    response = make_client().get("/jobs/1/documents")
    assert (response.status_code, response.json()["code"]) == (401, "not_authenticated")


def test_a_job_without_documents_has_an_empty_list(alice: JobsSession) -> None:
    alice.add()

    response = documents_of(alice, 1)

    assert response.status_code == 200
    assert response.json() == {"items": []}
    assert response.headers["cache-control"] == "no-store"


def test_a_missing_job_is_404(alice: JobsSession) -> None:
    assert documents_of(alice, 99).status_code == 404
    assert documents_of(alice, 10**30).status_code == 404
    assert documents_of(alice, 0).status_code == 404


def test_a_version_has_its_fields_the_report_and_no_content(
    alice: JobsSession, alice_shelf: Shelf
) -> None:
    alice.add()
    name_of(alice, "Alex Example")
    alice_shelf.save(1)

    [item] = documents_of(alice, 1).json()["items"]

    assert item == {
        "document_id": 1,
        "job_id": 1,
        "kind": "cv",
        "version": 1,
        "created_at": "2026-03-04T05:06:00Z",
        "file_name": "Alex_Example_CV.pdf",
        "pdf_available": True,
        "photo_id": None,
        "lint": {
            "passed": False,
            "pages": 3,
            "issues": [
                {"code": "pages", "message": "3 сторінок, а можна до 2 — скороти."}
            ],
            "keywords": {
                "covered": ["Python"],
                "missing": ["Kafka", "Go"],
                "percent": 33,
            },
        },
    }


def test_versions_come_newest_first_with_independent_numbering_by_kind(
    alice: JobsSession, alice_shelf: Shelf
) -> None:
    alice.add()
    for content in (CV, CV, LETTER, CV, LETTER):
        alice_shelf.save(1, content)

    items = documents_of(alice, 1).json()["items"]

    assert [(i["document_id"], i["kind"], i["version"]) for i in items] == [
        (5, "cl", 2),
        (4, "cv", 3),
        (3, "cl", 1),
        (2, "cv", 2),
        (1, "cv", 1),
    ]


def test_a_version_without_a_report_has_a_null_lint(
    alice: JobsSession, alice_shelf: Shelf
) -> None:
    alice.add()
    alice_shelf.save(1, CV, None)

    [item] = documents_of(alice, 1).json()["items"]

    assert item["lint"] is None


def test_a_report_without_keywords_has_null_keywords(
    alice: JobsSession, alice_shelf: Shelf
) -> None:
    alice.add()
    alice_shelf.save(1, CV, LintReport(pages=1))

    [item] = documents_of(alice, 1).json()["items"]

    assert item["lint"] == {"passed": True, "pages": 1, "issues": [], "keywords": None}


def test_a_missing_file_is_flagged_on_that_version_only(
    alice: JobsSession, alice_shelf: Shelf
) -> None:
    alice.add()
    alice_shelf.save(1, CV, pdf=False)
    alice_shelf.save(1, CV)

    second, first = documents_of(alice, 1).json()["items"]

    assert (first["pdf_available"], second["pdf_available"]) == (False, True)


def test_a_profile_without_a_name_still_lists_with_a_plain_file_name(
    alice: JobsSession, alice_shelf: Shelf
) -> None:
    alice.add()
    alice_shelf.save(1)

    assert documents_of(alice, 1).json()["items"][0]["file_name"] == "CV.pdf"


def test_a_user_never_sees_documents_of_another(
    alice: JobsSession, bob: JobsSession, alice_shelf: Shelf, bob_shelf: Shelf
) -> None:
    alice.add(text="alice job")
    bob.add(text="bob job")
    alice_shelf.save(1)
    bob_shelf.save(1, LETTER)

    assert [i["kind"] for i in documents_of(alice, 1).json()["items"]] == ["cv"]
    assert [i["kind"] for i in documents_of(bob, 1).json()["items"]] == ["cl"]


def test_a_number_that_is_not_an_integer_is_rejected(alice: JobsSession) -> None:
    assert documents_of(alice, "abc").status_code == 422


# --- фото в шапці CV ---------------------------------------------------------------------


def upload_photo(session: JobsSession) -> None:
    response = session.client.post(
        "/photos",
        files={"file": ("photo.jpg", jpeg(*HALF_FRAME), "image/jpeg")},
        headers=session.csrf,
    )
    assert response.status_code == 201


def test_a_cv_shows_its_photo_and_a_cv_without_one_shows_null(
    alice: JobsSession, alice_shelf: Shelf
) -> None:
    alice.add()
    upload_photo(alice)
    alice_shelf.save(1, CV, photo_number=1)
    alice_shelf.save(1, CV)
    alice_shelf.save(1, LETTER)

    items = documents_of(alice, 1).json()["items"]

    assert [(i["kind"], i["version"], i["photo_id"]) for i in items] == [
        ("cl", 1, None),
        ("cv", 2, None),
        ("cv", 1, 1),
    ]


def test_deleting_the_photo_keeps_the_cv_and_its_pdf_and_clears_photo_id(
    alice: JobsSession, alice_shelf: Shelf
) -> None:
    alice.add()
    upload_photo(alice)
    document = alice_shelf.save(1, CV, photo_number=1)

    deleted = alice.client.delete("/photos/1", headers=alice.csrf)

    assert deleted.status_code == 204
    [item] = documents_of(alice, 1).json()["items"]
    assert (item["photo_id"], item["pdf_available"]) == (None, True)
    assert alice.client.get(f"/documents/{document}/pdf").content == b"%PDF-1.7"
