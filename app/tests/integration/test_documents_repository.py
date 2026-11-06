"""PostgresDocuments на справжній базі: номери на користувача, версії, унікальності, формат вмісту для ETL."""

import asyncio
import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

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
from domain.documents.ids import DocumentId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, posting, uow

__all__ = ["uow"]

_ids = iter(range(1, 10_000))


def _id() -> UUID:
    return UUID(int=0xD000 + next(_ids))


# Колонки `documents` v1, які переносить ETL у B12 (`photo_id` — з B7b, перевіряється нижче).
V1_DOCUMENT_COLUMNS = {"kind", "version", "content", "created_at", "lint"}

CV = Cv(
    headline=Claim("Senior Backend Engineer", (1,)),
    summary=Claim("Payments backend", (2, 3)),
    sections=(
        CvSection(
            CvSectionName.EXPERIENCE,
            (
                CvEntry(
                    Claim("Engineer · Acme", (4,)),
                    (Claim("Built APIs", (5,)), Claim("Cut latency", (6,))),
                    meta=Claim("2021 - 2024", (7,)),
                    subtitle=Claim("Payments team of 5", (8,)),
                ),
            ),
        ),
        CvSection(CvSectionName.SKILLS, (CvEntry(Claim("Backend", (9,))),)),
    ),
)
LETTER = CoverLetter(
    ("Dear team,", " ".join(["word"] * 150), "Best regards,\nAlex"), (1, 2)
)


async def _job(
    uow: UnitOfWorkFactory, user: UserId, body: str = "job"
) -> tuple[int, JobId]:
    job_id = JobId(_id())
    async with uow() as tx:
        number = await tx.jobs.add(user, job_id, posting(body), NOW)
        await tx.commit()
    return number, job_id


async def _save(
    uow: UnitOfWorkFactory,
    user: UserId,
    job: tuple[int, JobId],
    content: Cv | CoverLetter = CV,
    now: datetime = NOW,
    number: int | None = None,
) -> Document:
    async with uow() as tx:
        saved = await tx.documents.add(
            user, DocumentId(_id()), job[1], content, now, number
        )
        await tx.commit()
        return saved


async def _list(
    uow: UnitOfWorkFactory, user: UserId, job: tuple[int, JobId]
) -> list[Document]:
    async with uow() as tx:
        return await tx.documents.list_for_job(user, job[1])


async def _scalar(engine: AsyncEngine, sql: str) -> object:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar()


async def _run(engine: AsyncEngine, sql: str, params: Mapping[str, object]) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


def test_a_job_without_documents_has_an_empty_list(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    assert portal.call(_list, uow, ALICE, job) == []


def test_a_saved_cv_reads_back_whole(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)

    saved = portal.call(_save, uow, ALICE, job, CV)

    assert (saved.number, saved.job_number, saved.kind, saved.version) == (
        1,
        job[0],
        DocumentKind.CV,
        1,
    )
    assert saved.content == CV
    assert saved.created_at == NOW
    assert portal.call(_list, uow, ALICE, job) == [saved]


def test_a_saved_letter_reads_back_whole(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)

    saved = portal.call(_save, uow, ALICE, job, LETTER)

    assert (saved.kind, saved.version, saved.content) == (
        DocumentKind.COVER_LETTER,
        1,
        LETTER,
    )
    assert portal.call(_list, uow, ALICE, job) == [saved]


def test_versions_of_a_cv_and_a_letter_of_one_job_are_independent(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)

    saved = [
        portal.call(_save, uow, ALICE, job, content)
        for content in (CV, CV, LETTER, CV, LETTER)
    ]

    assert [(d.kind.value, d.version) for d in saved] == [
        ("cv", 1),
        ("cv", 2),
        ("cl", 1),
        ("cv", 3),
        ("cl", 2),
    ]


def test_another_job_starts_its_versions_from_one(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_job, uow, ALICE, "first")
    other = portal.call(_job, uow, ALICE, "other")
    portal.call(_save, uow, ALICE, first)
    portal.call(_save, uow, ALICE, first)

    saved = portal.call(_save, uow, ALICE, other)

    assert (saved.job_number, saved.version) == (other[0], 1)


def test_numbers_count_per_user_across_jobs_and_kinds(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_job, uow, ALICE, "first")
    other = portal.call(_job, uow, ALICE, "other")
    theirs = portal.call(_job, uow, BOB, "theirs")

    mine = [
        portal.call(_save, uow, ALICE, first, CV).number,
        portal.call(_save, uow, ALICE, first, LETTER).number,
        portal.call(_save, uow, ALICE, other, CV).number,
    ]

    assert mine == [1, 2, 3]
    assert portal.call(_save, uow, BOB, theirs).number == 1


def test_an_explicit_number_moves_the_counter_forward_never_back(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)

    explicit = portal.call(_save, uow, ALICE, job, CV, NOW, 40)
    later = portal.call(_save, uow, ALICE, job)
    older = portal.call(_save, uow, ALICE, job, CV, NOW, 5)
    after = portal.call(_save, uow, ALICE, job)

    assert [d.number for d in (explicit, later, older, after)] == [40, 41, 5, 42]


def test_the_list_has_every_version_newest_first(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    cv_1 = portal.call(_save, uow, ALICE, job, CV, NOW)
    letter = portal.call(_save, uow, ALICE, job, LETTER, NOW + timedelta(minutes=1))
    cv_2 = portal.call(_save, uow, ALICE, job, CV, NOW + timedelta(minutes=2))

    assert portal.call(_list, uow, ALICE, job) == [cv_2, letter, cv_1]


def test_the_list_has_only_the_documents_of_that_job(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_job, uow, ALICE, "first")
    other = portal.call(_job, uow, ALICE, "other")
    portal.call(_save, uow, ALICE, first)
    on_other = portal.call(_save, uow, ALICE, other)

    assert portal.call(_list, uow, ALICE, other) == [on_other]


def test_a_user_does_not_see_the_documents_of_another(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    mine = portal.call(_job, uow, ALICE)
    portal.call(_save, uow, ALICE, mine)

    assert portal.call(_list, uow, BOB, mine) == []


def test_concurrent_saves_of_one_job_get_distinct_versions_and_numbers(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)

    async def both() -> list[Document]:
        return list(
            await asyncio.gather(
                _save(uow, ALICE, job), _save(uow, ALICE, job), _save(uow, ALICE, job)
            )
        )

    saved = portal.call(both)

    assert sorted(d.version for d in saved) == [1, 2, 3]
    assert sorted(d.number for d in saved) == [1, 2, 3]


def test_an_unsaved_transaction_leaves_no_document_and_spends_no_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)

    async def abandoned() -> None:
        async with uow() as tx:
            await tx.documents.add(ALICE, DocumentId(_id()), job[1], CV, NOW)

    portal.call(abandoned)

    assert portal.call(_list, uow, ALICE, job) == []
    assert portal.call(_save, uow, ALICE, job).number == 1


# --- схема ---------------------------------------------------------------------------


def test_the_cv_is_stored_in_the_v1_json_shape(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save, uow, ALICE, job, CV)

    stored = portal.call(_scalar, engine, "SELECT content FROM documents")

    assert stored == {
        "headline": {"text": "Senior Backend Engineer", "fact_ids": [1]},
        "summary": {"text": "Payments backend", "fact_ids": [2, 3]},
        "sections": [
            {
                "name": "Experience",
                "entries": [
                    {
                        "heading": {"text": "Engineer · Acme", "fact_ids": [4]},
                        "bullets": [
                            {"text": "Built APIs", "fact_ids": [5]},
                            {"text": "Cut latency", "fact_ids": [6]},
                        ],
                        "meta": {"text": "2021 - 2024", "fact_ids": [7]},
                        "subtitle": {"text": "Payments team of 5", "fact_ids": [8]},
                    }
                ],
            },
            {
                "name": "Skills",
                "entries": [
                    {
                        "heading": {"text": "Backend", "fact_ids": [9]},
                        "bullets": [],
                        "meta": None,
                        "subtitle": None,
                    }
                ],
            },
        ],
    }


def test_the_letter_is_stored_in_the_v1_json_shape(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save, uow, ALICE, job, LETTER)

    stored = portal.call(
        _scalar, engine, "SELECT content FROM documents WHERE kind = 'cl'"
    )

    assert stored == {"paragraphs": list(LETTER.paragraphs), "fact_ids": [1, 2]}
    assert portal.call(_scalar, engine, "SELECT kind FROM documents") == "cl"


def test_a_v1_cv_without_meta_and_subtitle_keys_reads_back(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE)
    v1 = {
        "headline": {"text": "Engineer", "fact_ids": [1]},
        "summary": {"text": "Summary", "fact_ids": [1]},
        "sections": [
            {
                "name": "Skills",
                "entries": [
                    {
                        "heading": {"text": "Backend", "fact_ids": [1]},
                        "bullets": [{"text": "Python", "fact_ids": [1]}],
                    }
                ],
            }
        ],
    }
    portal.call(
        _run,
        engine,
        "INSERT INTO documents (id, user_id, document_number, job_id, kind, version,"
        " content, created_at)"
        " SELECT gen_random_uuid(), user_id, 7, id, 'cv', 1, CAST(:content AS jsonb), now()"
        " FROM jobs",
        {"content": json.dumps(v1)},
    )

    [saved] = portal.call(_list, uow, ALICE, job)

    assert saved.number == 7
    assert isinstance(saved.content, Cv)
    entry = saved.content.sections[0].entries[0]
    assert (entry.meta, entry.subtitle) == (None, None)
    assert entry.bullets == (Claim("Python", (1,)),)


def test_the_table_has_the_v1_columns_for_the_etl(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    columns = portal.call(
        _scalar,
        engine,
        "SELECT array_agg(column_name::text) FROM information_schema.columns"
        " WHERE table_name = 'documents'",
    )
    assert set(columns) >= V1_DOCUMENT_COLUMNS  # type: ignore[call-overload]


def test_a_saved_document_has_no_lint_report_yet(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save, uow, ALICE, job)

    assert portal.call(_scalar, engine, "SELECT lint IS NULL FROM documents") is True


def test_the_schema_rejects_a_repeated_number_of_one_user(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save, uow, ALICE, job, CV, NOW, 3)

    with pytest.raises(IntegrityError, match="document_number"):
        portal.call(_save, uow, ALICE, job, LETTER, NOW, 3)


def test_the_schema_rejects_a_repeated_version_of_one_kind_of_one_job(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save, uow, ALICE, job)

    with pytest.raises(IntegrityError, match="version"):
        portal.call(
            _run,
            engine,
            "INSERT INTO documents (id, user_id, document_number, job_id, kind, version,"
            " content, created_at)"
            " SELECT gen_random_uuid(), user_id, 99, id, 'cv', 1, '{}', now() FROM jobs",
            {},
        )


@pytest.mark.parametrize(
    ("kind", "version", "constraint"),
    [("xx", 1, "kind"), ("cv", 0, "version"), ("cv", -1, "version")],
)
def test_the_schema_rejects_an_unknown_kind_and_a_version_below_one(
    portal: BlockingPortal,
    uow: UnitOfWorkFactory,
    engine: AsyncEngine,
    kind: str,
    version: int,
    constraint: str,
) -> None:
    portal.call(_job, uow, ALICE)

    with pytest.raises(IntegrityError, match=constraint):
        portal.call(
            _run,
            engine,
            "INSERT INTO documents (id, user_id, document_number, job_id, kind, version,"
            " content, created_at)"
            " SELECT gen_random_uuid(), user_id, 1, id, :kind, :version, '{}', now()"
            " FROM jobs",
            {"kind": kind, "version": version},
        )


def test_the_schema_rejects_a_number_below_one(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_job, uow, ALICE)

    with pytest.raises(IntegrityError, match="document_number"):
        portal.call(
            _run,
            engine,
            "INSERT INTO documents (id, user_id, document_number, job_id, kind, version,"
            " content, created_at)"
            " SELECT gen_random_uuid(), user_id, 0, id, 'cv', 1, '{}', now() FROM jobs",
            {},
        )


def test_removing_a_job_or_a_user_removes_its_documents(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    mine = portal.call(_job, uow, ALICE, "a")
    theirs = portal.call(_job, uow, BOB, "b")
    portal.call(_save, uow, ALICE, mine)
    portal.call(_save, uow, BOB, theirs)

    portal.call(
        _run,
        engine,
        "DELETE FROM jobs WHERE job_number = :n AND user_id = :u",
        {"n": mine[0], "u": ALICE.value},
    )
    assert portal.call(_scalar, engine, "SELECT count(*) FROM documents") == 1
    portal.call(_run, engine, "DELETE FROM users WHERE id = :u", {"u": BOB.value})
    assert portal.call(_scalar, engine, "SELECT count(*) FROM documents") == 0
    assert portal.call(_scalar, engine, "SELECT count(*) FROM document_counters") == 1


# --- один документ кожного виду: видалення старих версій -----------------------------------


async def _delete_for_job(
    uow: UnitOfWorkFactory,
    user: UserId,
    job: tuple[int, JobId],
    kind: DocumentKind,
    keep: Document,
) -> list[DocumentId]:
    async with uow() as tx:
        gone = await tx.documents.delete_for_job(user, job[1], kind, keep.id)
        await tx.commit()
        return gone


def test_delete_for_job_removes_the_other_documents_of_that_kind_and_returns_their_ids(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    first = portal.call(_save, uow, ALICE, job, CV)
    second = portal.call(_save, uow, ALICE, job, CV)
    newest = portal.call(_save, uow, ALICE, job, CV)

    gone = portal.call(_delete_for_job, uow, ALICE, job, DocumentKind.CV, newest)

    assert sorted(gone, key=lambda i: i.value) == sorted(
        [first.id, second.id], key=lambda i: i.value
    )
    assert portal.call(_list, uow, ALICE, job) == [newest]


def test_delete_for_job_keeps_the_version_counter_going(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save, uow, ALICE, job, CV)
    newest = portal.call(_save, uow, ALICE, job, CV)
    portal.call(_delete_for_job, uow, ALICE, job, DocumentKind.CV, newest)

    after = portal.call(_save, uow, ALICE, job, CV)

    assert (newest.version, after.version, after.number) == (2, 3, 3)


def test_delete_for_job_leaves_the_other_kind_other_jobs_and_other_users(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    mine = portal.call(_job, uow, ALICE, "a")
    other_job = portal.call(_job, uow, ALICE, "b")
    theirs = portal.call(_job, uow, BOB, "c")
    portal.call(_save, uow, ALICE, mine, CV)
    letter = portal.call(_save, uow, ALICE, mine, LETTER)
    on_other_job = portal.call(_save, uow, ALICE, other_job, CV)
    bobs = portal.call(_save, uow, BOB, theirs, CV)
    newest = portal.call(_save, uow, ALICE, mine, CV)

    portal.call(_delete_for_job, uow, ALICE, mine, DocumentKind.CV, newest)

    assert portal.call(_list, uow, ALICE, mine) == [newest, letter]
    assert portal.call(_list, uow, ALICE, other_job) == [on_other_job]
    assert portal.call(_list, uow, BOB, theirs) == [bobs]


def test_delete_for_job_with_nothing_else_deletes_nothing(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    only = portal.call(_save, uow, ALICE, job, CV)

    assert portal.call(_delete_for_job, uow, ALICE, job, DocumentKind.CV, only) == []
    assert portal.call(_list, uow, ALICE, job) == [only]


def test_delete_for_job_takes_the_download_links_of_the_deleted_documents(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE)
    old = portal.call(_save, uow, ALICE, job, CV)
    newest = portal.call(_save, uow, ALICE, job, CV)
    for document, digest in ((old, "old"), (newest, "new")):
        portal.call(
            _run,
            engine,
            "INSERT INTO document_download_links"
            " (token_digest, user_id, document_id, expires_at)"
            " VALUES (:d, :u, :doc, now() + interval '10 minutes')",
            {"d": digest, "u": ALICE.value, "doc": document.id.value},
        )

    portal.call(_delete_for_job, uow, ALICE, job, DocumentKind.CV, newest)

    assert (
        portal.call(
            _scalar,
            engine,
            "SELECT string_agg(token_digest, ',') FROM document_download_links",
        )
        == "new"
    )


async def _superseded(uow: UnitOfWorkFactory) -> list[DocumentId]:
    async with uow() as tx:
        return await tx.documents.superseded()


async def _delete(uow: UnitOfWorkFactory, ids: list[DocumentId]) -> None:
    async with uow() as tx:
        await tx.documents.delete(ids)
        await tx.commit()


def test_superseded_lists_all_but_the_newest_of_each_user_job_and_kind(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first_job = portal.call(_job, uow, ALICE, "a")
    second_job = portal.call(_job, uow, ALICE, "b")
    bobs_job = portal.call(_job, uow, BOB, "c")
    old_cv = portal.call(_save, uow, ALICE, first_job, CV)
    old_letter = portal.call(_save, uow, ALICE, first_job, LETTER)
    portal.call(_save, uow, ALICE, first_job, CV)
    portal.call(_save, uow, ALICE, first_job, LETTER)
    portal.call(_save, uow, ALICE, first_job, CV)
    portal.call(_save, uow, ALICE, second_job, CV)
    bobs_old = portal.call(_save, uow, BOB, bobs_job, CV)
    portal.call(_save, uow, BOB, bobs_job, CV)
    middle_cv = portal.call(
        _list, uow, ALICE, first_job
    )  # newest first: cv v3, cl v2, cv v2, cl v1, cv v1
    assert [d.version for d in middle_cv] == [3, 2, 2, 1, 1]

    found = portal.call(_superseded, uow)

    assert {i.value for i in found} == {
        old_cv.id.value,
        old_letter.id.value,
        middle_cv[2].id.value,
        bobs_old.id.value,
    }


def test_delete_removes_the_given_documents_only(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    old = portal.call(_save, uow, ALICE, job, CV)
    newest = portal.call(_save, uow, ALICE, job, CV)

    portal.call(_delete, uow, [old.id])

    assert portal.call(_list, uow, ALICE, job) == [newest]
    portal.call(_delete, uow, [])
    assert portal.call(_list, uow, ALICE, job) == [newest]
