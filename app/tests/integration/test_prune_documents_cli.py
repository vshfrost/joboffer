"""CLI `python -m bootstrap.prune_documents`: без `--apply` лише рахує, з `--apply` лишає найновіший
документ кожного (користувач, вакансія, вид) і прибирає решту разом з файлами PDF."""

from pathlib import Path
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bootstrap.prune_documents import main
from domain.documents.document import Document
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from infrastructure.pdf.files import FileDocuments
from tests.integration.test_documents_repository import (
    CV,
    LETTER,
    _job,
    _save,
)
from tests.integration.test_jobs_repository import ALICE, BOB, uow

__all__ = ["uow"]


@pytest.fixture
def documents_dir(
    portal: BlockingPortal,
    engine: AsyncEngine,
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    root = tmp_path / "documents"
    monkeypatch.setenv("JOBOFFER_DATABASE_URL", database_url)
    monkeypatch.setenv("JOBOFFER_DOCUMENTS_DIR", str(root))
    return root


def seed(portal: BlockingPortal, uow: UnitOfWorkFactory, root: Path) -> list[Document]:
    """Алісі: CV ×3 і лист ×2 однієї вакансії; Бобу: CV ×2. Кожному документу — файл."""
    mine = portal.call(_job, uow, ALICE, "a")
    theirs = portal.call(_job, uow, BOB, "b")
    saved = [
        portal.call(_save, uow, user, job, content)
        for user, job, content in (
            (ALICE, mine, CV),
            (ALICE, mine, LETTER),
            (ALICE, mine, CV),
            (ALICE, mine, LETTER),
            (ALICE, mine, CV),
            (BOB, theirs, CV),
            (BOB, theirs, CV),
        )
    ]
    files = FileDocuments(root)
    for document in saved:
        portal.call(files.write, document.id, b"%PDF-1.7")
    return saved


def documents_left(portal: BlockingPortal, engine: AsyncEngine) -> list[UUID]:
    async def run() -> list[UUID]:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT id FROM documents ORDER BY created_at, id")
            )
            return [row[0] for row in rows]

    return portal.call(run)


def test_without_apply_it_only_counts_and_deletes_nothing(
    portal: BlockingPortal,
    engine: AsyncEngine,
    uow: UnitOfWorkFactory,
    documents_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed(portal, uow, documents_dir)

    assert main([]) == 0

    assert (
        "Буде видалено (запусти з --apply): документів 4, файлів PDF на диску 4."
        in (capsys.readouterr().out)
    )
    assert len(documents_left(portal, engine)) == 7
    assert len(list(documents_dir.iterdir())) == 7


def test_with_apply_only_the_newest_of_each_user_job_and_kind_stays(
    portal: BlockingPortal,
    engine: AsyncEngine,
    uow: UnitOfWorkFactory,
    documents_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    saved = seed(portal, uow, documents_dir)
    newest = {saved[4], saved[3], saved[6]}  # cv v3 і cl v2 Аліси, cv v2 Боба

    assert main(["--apply"]) == 0

    assert "Видалено: документів 4, файлів PDF на диску 4." in capsys.readouterr().out
    assert {d.id.value for d in newest} == set(documents_left(portal, engine))
    assert {p.name for p in documents_dir.iterdir()} == {
        f"{d.id.value}.pdf" for d in newest
    }


def test_a_second_run_finds_nothing(
    portal: BlockingPortal,
    uow: UnitOfWorkFactory,
    documents_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed(portal, uow, documents_dir)
    main(["--apply"])
    capsys.readouterr()

    assert main(["--apply"]) == 0

    assert "Видалено: документів 0, файлів PDF на диску 0." in capsys.readouterr().out
