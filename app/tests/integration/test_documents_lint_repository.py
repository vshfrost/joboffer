"""ATS-звіт і `get` у PostgresDocuments: знімок звіту в JSON тієї ж форми, що в v1 (для ETL)."""

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.documents.document import Document
from domain.documents.ids import DocumentId
from domain.documents.lint import KeywordCoverage, LintCode, LintIssue, LintReport
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_documents_repository import (
    CV,
    LETTER,
    _id,
    _job,
    _list,
    _save,
    _scalar,
    uow,
)
from tests.integration.test_jobs_repository import ALICE, BOB, NOW

__all__ = ["uow"]

FULL = LintReport(
    pages=3,
    issues=(
        LintIssue(LintCode.PAGES, "3 сторінок, а можна до 2 — скороти."),
        LintIssue(LintCode.INVISIBLE_CHARS, "Невидимі символи U+200B у PDF."),
    ),
    keywords=KeywordCoverage(("Kafka", "C#"), ("Go",)),
)
CLEAN = LintReport(pages=1)


async def _save_linted(
    uow: UnitOfWorkFactory,
    user: UserId,
    job: tuple[int, JobId],
    lint: LintReport,
) -> Document:
    async with uow() as tx:
        saved = await tx.documents.add(
            user, DocumentId(_id()), job[1], CV, NOW, lint=lint
        )
        await tx.commit()
        return saved


async def _get(uow: UnitOfWorkFactory, user: UserId, number: int) -> Document | None:
    async with uow() as tx:
        return await tx.documents.get(user, number)


def test_a_report_reads_back_whole(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)

    saved = portal.call(_save_linted, uow, ALICE, job, FULL)

    assert saved.lint == FULL
    assert portal.call(_list, uow, ALICE, job) == [saved]
    assert portal.call(_list, uow, ALICE, job)[0].lint == FULL


def test_a_clean_report_without_keywords_reads_back_as_such(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)

    portal.call(_save_linted, uow, ALICE, job, CLEAN)

    [saved] = portal.call(_list, uow, ALICE, job)
    assert saved.lint == CLEAN
    assert saved.lint is not None
    assert (saved.lint.passed, saved.lint.keywords) == (True, None)


def test_a_version_saved_without_a_report_has_none(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)

    saved = portal.call(_save, uow, ALICE, job, LETTER)

    assert saved.lint is None
    assert portal.call(_list, uow, ALICE, job)[0].lint is None


def test_every_version_keeps_its_own_snapshot(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)

    portal.call(_save_linted, uow, ALICE, job, FULL)
    portal.call(_save_linted, uow, ALICE, job, CLEAN)

    assert [d.lint for d in portal.call(_list, uow, ALICE, job)] == [CLEAN, FULL]


def test_the_report_is_stored_in_the_v1_json_shape(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save_linted, uow, ALICE, job, FULL)

    stored = portal.call(_scalar, engine, "SELECT lint FROM documents")

    assert stored == {
        "pages": 3,
        "issues": [
            {"code": "pages", "message": "3 сторінок, а можна до 2 — скороти."},
            {"code": "invisible_chars", "message": "Невидимі символи U+200B у PDF."},
        ],
        "keywords": {"covered": ["Kafka", "C#"], "missing": ["Go"]},
    }


def test_a_report_without_keywords_is_stored_with_a_null(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save_linted, uow, ALICE, job, CLEAN)

    assert portal.call(_scalar, engine, "SELECT lint FROM documents") == {
        "pages": 1,
        "issues": [],
        "keywords": None,
    }


def test_get_finds_a_document_by_its_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    first = portal.call(_save_linted, uow, ALICE, job, FULL)
    second = portal.call(_save, uow, ALICE, job, LETTER)

    assert portal.call(_get, uow, ALICE, first.number) == first
    assert portal.call(_get, uow, ALICE, second.number) == second


def test_get_does_not_find_a_missing_or_foreign_document(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    saved = portal.call(_save, uow, ALICE, job)

    assert portal.call(_get, uow, ALICE, 99) is None
    assert portal.call(_get, uow, BOB, saved.number) is None


@pytest.mark.parametrize("number", [0, -1, 2**31, 10**30])
def test_get_does_not_find_a_number_outside_the_range(
    portal: BlockingPortal, uow: UnitOfWorkFactory, number: int
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save, uow, ALICE, job)

    assert portal.call(_get, uow, ALICE, number) is None


def test_the_same_number_of_two_users_is_two_different_documents(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    mine = portal.call(_job, uow, ALICE, "a")
    theirs = portal.call(_job, uow, BOB, "b")
    own = portal.call(_save_linted, uow, ALICE, mine, FULL)
    other = portal.call(_save_linted, uow, BOB, theirs, CLEAN)

    assert own.number == other.number == 1
    assert portal.call(_get, uow, BOB, 1) == other
