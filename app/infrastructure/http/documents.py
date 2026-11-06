"""HTTP документів: PDF версії й список версій вакансії — лише власнику з чинною сесією.

`document_id` у URL — номер документа в межах користувача (ціле, з 1), `job_id` — номер вакансії.
Документа чи файлу нема, або документ чужий, — 404 (однаково): інша версія замість відсутньої не
підставляється. PDF генерує Claude через MCP (`save_cv`, `save_cover_letter`); у вебі його лише
відкривають, а список дає версії без вмісту: назву файлу, наявність PDF і ATS-звіт кожної.
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from application.contracts.actor import Actor
from application.contracts.documents import JobDocumentData, LintData
from application.documents.use_cases import DocumentUseCases
from infrastructure.http.auth import HttpAuth


class LintIssueModel(BaseModel):
    code: str
    message: str


class KeywordCoverageModel(BaseModel):
    covered: list[str]
    missing: list[str]
    percent: int


class LintModel(BaseModel):
    """ATS-звіт на момент збереження версії: `passed` = нема issues, покриття — окремо."""

    passed: bool
    pages: int
    issues: list[LintIssueModel]
    # null — вакансію не аналізовано, покриття не рахувалося.
    keywords: KeywordCoverageModel | None


class DocumentModel(BaseModel):
    document_id: int
    job_id: int
    kind: Literal["cv", "cl"]
    version: int
    created_at: datetime
    file_name: str
    # false — файл PDF цієї версії зник з диска.
    pdf_available: bool
    # Номер фото в шапці CV; null — без фото (листи фото не мають, видалене фото теж дає null).
    photo_id: int | None
    # null — версія без ATS-звіту (не «пройдено»).
    lint: LintModel | None


class DocumentListModel(BaseModel):
    items: list[DocumentModel]


def _lint(report: LintData) -> LintModel:
    keywords = report.keywords
    return LintModel(
        passed=report.passed,
        pages=report.pages,
        issues=[
            LintIssueModel(code=issue.code.value, message=issue.message)
            for issue in report.issues
        ],
        keywords=None
        if keywords is None
        else KeywordCoverageModel(
            covered=list(keywords.covered),
            missing=list(keywords.missing),
            percent=keywords.percent,
        ),
    )


def _model(item: JobDocumentData) -> DocumentModel:
    return DocumentModel(
        document_id=item.document_number,
        job_id=item.job_number,
        kind=item.kind.value,
        version=item.version,
        created_at=item.created_at,
        file_name=item.file_name,
        pdf_available=item.pdf_available,
        photo_id=item.photo_number,
        lint=None if item.lint is None else _lint(item.lint),
    )


def documents_router(documents: DocumentUseCases, auth: HttpAuth) -> APIRouter:
    router = APIRouter(tags=["documents"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    @router.get("/documents/{document_id}/pdf", response_class=Response)
    async def pdf(document_id: int, actor: Caller) -> Response:
        found = await documents.get_pdf(actor, document_id)
        return Response(
            found.data,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{found.file_name}"',
                "Cache-Control": "no-store",
            },
        )

    @router.get("/jobs/{job_id}/documents")
    async def versions(
        job_id: int, actor: Caller, response: Response
    ) -> DocumentListModel:
        response.headers["Cache-Control"] = "no-store"
        found = await documents.list_job_documents(actor, job_id)
        return DocumentListModel(items=[_model(item) for item in found])

    return router
