"""DocumentRepository на Postgres.

Номер документа видає `document_counters`: апсерт рядка користувача блокує його до кінця
транзакції, тож паралельні збереження одного користувача (а з ними й підрахунок версії) йдуть по
черзі, а скасована транзакція номер не витрачає. Явний номер (перенос з v1) лічильник не
відсуває назад. `content` — JSON тієї ж форми, що в v1: ETL переносить рядки без перетворень.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.documents.document import (
    MAX_DOCUMENT_NUMBER,
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
from domain.documents.lint import KeywordCoverage, LintCode, LintIssue, LintReport
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.photos.ids import PhotoId
from infrastructure.db.documents.tables import DocumentCounterRow, DocumentRow
from infrastructure.db.jobs.tables import JobRow
from infrastructure.db.photos.tables import PhotoRow


class PostgresDocuments:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        given = await self._reserve_number(user_id, number)
        kind = DocumentKind.CV if isinstance(content, Cv) else DocumentKind.COVER_LETTER
        latest = await self._session.scalar(
            select(func.max(DocumentRow.version)).where(
                DocumentRow.job_id == job_id.value, DocumentRow.kind == kind.value
            )
        )
        row = DocumentRow(
            id=document_id.value,
            user_id=user_id.value,
            document_number=given,
            job_id=job_id.value,
            kind=kind.value,
            version=(latest or 0) + 1,
            content=_cv_to_json(content)
            if isinstance(content, Cv)
            else _letter_to_json(content),
            lint=None if lint is None else _lint_to_json(lint),
            created_at=now,
            photo_id=None if photo_id is None else photo_id.value,
        )
        self._session.add(row)
        await self._session.flush()
        job_number = await self._session.scalar(
            select(JobRow.job_number).where(JobRow.id == job_id.value)
        )
        photo_number = (
            None
            if photo_id is None
            else await self._session.scalar(
                select(PhotoRow.photo_number).where(PhotoRow.id == photo_id.value)
            )
        )
        return _to_domain(row, int(job_number or 0), photo_number)

    async def _reserve_number(self, user_id: UserId, explicit: int | None) -> int:
        if explicit is None:
            counter = pg_insert(DocumentCounterRow).values(
                user_id=user_id.value, last_number=1
            )
            update_to = DocumentCounterRow.last_number + 1
        else:
            counter = pg_insert(DocumentCounterRow).values(
                user_id=user_id.value, last_number=max(explicit, 0)
            )
            update_to = func.greatest(DocumentCounterRow.last_number, explicit)
        reserved = await self._session.scalar(
            counter.on_conflict_do_update(
                index_elements=[DocumentCounterRow.user_id],
                set_={"last_number": update_to},
            ).returning(DocumentCounterRow.last_number)
        )
        return explicit if explicit is not None else int(reserved or 0)

    async def get(self, user_id: UserId, number: int) -> Document | None:
        if not 1 <= number <= MAX_DOCUMENT_NUMBER:
            return None
        found = (
            await self._session.execute(
                select(DocumentRow, JobRow.job_number, PhotoRow.photo_number)
                .join(JobRow, JobRow.id == DocumentRow.job_id)
                .outerjoin(PhotoRow, PhotoRow.id == DocumentRow.photo_id)
                .where(
                    DocumentRow.user_id == user_id.value,
                    DocumentRow.document_number == number,
                )
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if found is None:
            return None
        row, job_number, photo_number = found
        return _to_domain(row, job_number, photo_number)

    async def list_for_job(self, user_id: UserId, job_id: JobId) -> list[Document]:
        found = await self._session.execute(
            select(DocumentRow, JobRow.job_number, PhotoRow.photo_number)
            .join(JobRow, JobRow.id == DocumentRow.job_id)
            .outerjoin(PhotoRow, PhotoRow.id == DocumentRow.photo_id)
            .where(
                DocumentRow.user_id == user_id.value,
                DocumentRow.job_id == job_id.value,
            )
            .order_by(DocumentRow.document_number.desc())
            .execution_options(populate_existing=True)
        )
        return [_to_domain(row, number, photo) for row, number, photo in found]

    async def delete_for_job(
        self, user_id: UserId, job_id: JobId, kind: DocumentKind, keep: DocumentId
    ) -> list[DocumentId]:
        found = await self._session.scalars(
            select(DocumentRow.id).where(
                DocumentRow.user_id == user_id.value,
                DocumentRow.job_id == job_id.value,
                DocumentRow.kind == kind.value,
                DocumentRow.id != keep.value,
            )
        )
        ids = [DocumentId(found_id) for found_id in found]
        await self.delete(ids)
        return ids

    async def superseded(self) -> list[DocumentId]:
        rank = (
            func.row_number()
            .over(
                partition_by=(
                    DocumentRow.user_id,
                    DocumentRow.job_id,
                    DocumentRow.kind,
                ),
                order_by=DocumentRow.version.desc(),
            )
            .label("rank")
        )
        ranked = select(DocumentRow.id, rank).subquery()
        found = await self._session.scalars(
            select(ranked.c.id).where(ranked.c.rank > 1)
        )
        return [DocumentId(found_id) for found_id in found]

    async def delete(self, document_ids: Sequence[DocumentId]) -> None:
        await self._session.execute(
            sa_delete(DocumentRow).where(
                DocumentRow.id.in_([item.value for item in document_ids])
            )
        )


def _to_domain(row: DocumentRow, job_number: int, photo_number: int | None) -> Document:
    kind = DocumentKind(row.kind)
    return Document(
        id=DocumentId(row.id),
        number=row.document_number,
        job_number=job_number,
        kind=kind,
        version=row.version,
        content=_cv_from_json(row.content)
        if kind is DocumentKind.CV
        else _letter_from_json(row.content),
        created_at=row.created_at,
        lint=None if row.lint is None else _lint_from_json(row.lint),
        photo_number=photo_number,
    )


def _lint_to_json(report: LintReport) -> dict[str, object]:
    keywords = report.keywords
    return {
        "pages": report.pages,
        "issues": [
            {"code": issue.code.value, "message": issue.message}
            for issue in report.issues
        ],
        "keywords": None
        if keywords is None
        else {"covered": list(keywords.covered), "missing": list(keywords.missing)},
    }


def _lint_from_json(data: dict[str, Any]) -> LintReport:
    keywords = data["keywords"]
    return LintReport(
        pages=data["pages"],
        issues=tuple(
            LintIssue(LintCode(issue["code"]), issue["message"])
            for issue in data["issues"]
        ),
        keywords=None
        if keywords is None
        else KeywordCoverage(tuple(keywords["covered"]), tuple(keywords["missing"])),
    )


def _claim_to_json(claim: Claim) -> dict[str, object]:
    return {"text": claim.text, "fact_ids": list(claim.fact_ids)}


def _optional_to_json(claim: Claim | None) -> dict[str, object] | None:
    return None if claim is None else _claim_to_json(claim)


def _claim_from_json(data: dict[str, Any]) -> Claim:
    return Claim(data["text"], tuple(data["fact_ids"]))


def _optional_from_json(data: dict[str, Any] | None) -> Claim | None:
    """`meta` і `subtitle` з'явилися у v1 пізніше: у старих рядках ключів нема."""
    return None if data is None else _claim_from_json(data)


def _cv_to_json(cv: Cv) -> dict[str, object]:
    return {
        "headline": _claim_to_json(cv.headline),
        "summary": _claim_to_json(cv.summary),
        "sections": [
            {
                "name": section.name.value,
                "entries": [
                    {
                        "heading": _claim_to_json(entry.heading),
                        "bullets": [_claim_to_json(bullet) for bullet in entry.bullets],
                        "meta": _optional_to_json(entry.meta),
                        "subtitle": _optional_to_json(entry.subtitle),
                    }
                    for entry in section.entries
                ],
            }
            for section in cv.sections
        ],
    }


def _cv_from_json(data: dict[str, Any]) -> Cv:
    return Cv(
        headline=_claim_from_json(data["headline"]),
        summary=_claim_from_json(data["summary"]),
        sections=tuple(
            CvSection(
                CvSectionName(section["name"]),
                tuple(
                    CvEntry(
                        _claim_from_json(entry["heading"]),
                        tuple(_claim_from_json(bullet) for bullet in entry["bullets"]),
                        _optional_from_json(entry.get("meta")),
                        _optional_from_json(entry.get("subtitle")),
                    )
                    for entry in section["entries"]
                ),
            )
            for section in data["sections"]
        ),
    )


def _letter_to_json(letter: CoverLetter) -> dict[str, object]:
    return {"paragraphs": list(letter.paragraphs), "fact_ids": list(letter.fact_ids)}


def _letter_from_json(data: dict[str, Any]) -> CoverLetter:
    return CoverLetter(tuple(data["paragraphs"]), tuple(data["fact_ids"]))
