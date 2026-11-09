"""Тули документів під вакансію: брифи для CV і cover letter, перевірка, збереження з PDF.

Назви, параметри й поля відповідей — як у v1, крім полів фото (їх повертає B7b) і перевірки
(`check_cv`, `check_cover_letter`). Claude отримує бриф, пише документ і перевіряє його, не
зберігаючи нічого; збереження повторює перевірки, відмовляє при будь-якому зауваженні, а
успішне замінює попередній документ того ж виду. Воно рендерить PDF і повертає `pdf_url` —
адресу в вебі, яка відкривається з чинною сесією. `job_id` — номер вакансії в межах
користувача, `document_id` — номер документа.
"""

from collections.abc import Callable
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.contracts.documents import (
    CheckData,
    ClaimData,
    CoverLetterBriefData,
    CoverLetterData,
    CvData,
    CvEntryData,
    CvSectionData,
    DocumentData,
    LintData,
    MustHaveFactsData,
)
from application.documents.use_cases import DocumentUseCases
from application.ports.prompts import PromptKey, Prompts
from domain.documents.document import MAX_LETTER_WORDS, MIN_LETTER_WORDS
from domain.documents.gate import GateStatus
from domain.shared.errors import DomainError
from domain.shared.local_time import local_day
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import CREATE, READ
from infrastructure.mcp.tools.analysis import AnalysisView, analysis_view
from infrastructure.mcp.tools.facts import FactView, fact_view
from infrastructure.mcp.tools.jobs import JobView, job_view
from infrastructure.mcp.tools.photos import PhotoLinks, PhotoList, photo_list
from infrastructure.mcp.tools.profile import Profile, profile_view

CvSectionNameValue = Literal[
    "Experience",
    "Projects",
    "Achievements",
    "Skills",
    "Education",
    "Education and Languages",
    "Certifications",
    "Languages",
]

LETTER_TEXT = (
    f"{MIN_LETTER_WORDS}–{MAX_LETTER_WORDS} words, paragraphs separated by blank lines, "
    'a single line break inside a paragraph is kept (sign-off "Best regards,\\nName")'
)


class ClaimIn(BaseModel):
    text: str
    fact_ids: list[int] = Field(description="Confirmed facts this line rests on, 1–10")


class CvEntryIn(BaseModel):
    heading: ClaimIn = Field(
        description="Role / project / skill group, e.g. 'Senior Backend Engineer · Acme'"
    )
    meta: ClaimIn | None = Field(
        default=None,
        description="Right of the heading: dates ('Jul 2024 - Nov 2025') or 'Independent project'",
    )
    subtitle: ClaimIn | None = Field(
        default=None, description="One grey line of context under the heading"
    )
    bullets: list[ClaimIn] = Field(
        default_factory=list, description="For a Skills group: its items"
    )


class CvSectionIn(BaseModel):
    name: CvSectionNameValue
    entries: list[CvEntryIn]


class CvIn(BaseModel):
    """CV for one job; every line cites the confirmed facts behind it."""

    headline: ClaimIn = Field(description="Target role, e.g. 'Senior Backend Engineer'")
    summary: ClaimIn = Field(description="2–4 sentences tailored to the job")
    sections: list[CvSectionIn]


class MustHaveFactsIn(BaseModel):
    """What you say about one must-have item of the analysis; the server checks it."""

    item: str = Field(description="The must_have text exactly as in the analysis")
    fact_ids: list[int] = Field(
        description="Confirmed facts under the item; at least one must stand in a CV line"
    )
    kind: Literal["fact", "analogue"] = Field(
        description="fact: the facts meet the requirement itself; analogue: they are "
        "the closest related experience, the requirement itself is a gap"
    )


class CoverLetterView(BaseModel):
    text: str = Field(description="Paragraphs separated by blank lines")
    fact_ids: list[int]


class LintIssueView(BaseModel):
    code: str = Field(
        description="invisible_chars, unexpected_text, missing_text, order, headings, "
        "fonts_not_embedded, pages, invalid_value, line_break, double_space, "
        "list_marker or placeholder"
    )
    message: str


class KeywordsView(BaseModel):
    covered: list[str] = Field(description="Analysis keywords found in the text")
    missing: list[str] = Field(
        description="Analysis keywords absent from the text; add one only where a "
        "confirmed fact backs it"
    )
    percent: int


class CheckView(BaseModel):
    """Result of check_cv / check_cover_letter: nothing was saved."""

    passed: bool = Field(description="True: save_cv / save_cover_letter accepts it")
    issues: list[LintIssueView] = Field(description="Fix all of them and check again")
    keywords: KeywordsView | None = Field(
        description="Coverage of the analysis keywords in the document text; "
        "null: job not analysed or the text could not be read"
    )


class GateView(BaseModel):
    """Is the CV ready to send: two numbers and the verdict. It never blocks save_cv."""

    status: GateStatus = Field(
        description="passed: evidence_percent is 100 and coverage_percent is at least "
        "90; no_data: the analysis has no fact map or keywords, which is not a pass"
    )
    evidence_percent: int | None = Field(
        description="Share of the keywords a confirmed fact backs that are in the "
        "text; null: no data"
    )
    evidence_missing: list[str] = Field(
        description="Keywords a confirmed fact backs that are absent from the text: "
        "add them where the fact allows"
    )
    coverage_percent: int | None = Field(
        description="Share of all analysis keywords (a group a | b counts once) in the "
        "text; null: no keywords"
    )


class MustHaveItemView(BaseModel):
    item: str = Field(description="A must_have item of the analysis")
    status: Literal["covered", "analogue", "missing"] = Field(
        description="covered: a CV line cites the facts you gave as kind fact; analogue: "
        "the same for kind analogue; missing: otherwise, see reason"
    )
    fact_ids: list[int] = Field(
        description="The facts of the entry a CV line cites; empty when missing"
    )
    reason: str | None = Field(description="Why the item is missing; null otherwise")


class MustHaveCoverageView(BaseModel):
    items: list[MustHaveItemView] = Field(
        description="Every must_have item of the analysis, in its order"
    )
    unknown: list[str] = Field(
        description="Items you named that are not in the analysis; ignored"
    )


class CvCheckView(CheckView):
    """Result of check_cv: the CheckView plus the gate and the must-have coverage."""

    gate: GateView | None = Field(
        default=None,
        description="null: the text could not be read",
    )
    must_have_coverage: MustHaveCoverageView | None = Field(
        default=None,
        description="Which must_have items of the analysis the CV covers, by the "
        "must_have_facts you passed (without them every item is missing); null: job "
        "not analysed or the text could not be read",
    )


class LintView(BaseModel):
    """ATS lint of the saved PDF: what a parser extracts compared with what was written."""

    passed: bool = Field(description="False: the PDF has issues")
    pages: int
    issues: list[LintIssueView]
    keywords_covered: list[str] | None = Field(
        description="Analysis keywords found in the PDF text; null: job not analysed"
    )
    keywords_missing: list[str] | None = Field(
        description="Analysis keywords absent from the PDF text; add one only where a "
        "confirmed fact backs it"
    )
    keyword_coverage_percent: int | None


class DocumentView(BaseModel):
    document_id: int
    job_id: int
    kind: Literal["cv", "cl"] = Field(description="cv or cl (cover letter)")
    version: int
    created: str = Field(description="YYYY-MM-DD")
    pdf_url: str = Field(
        description="Opens in the user's browser with their web session"
    )
    cv: CvIn | None = Field(description="Set for kind=cv")
    cover_letter: CoverLetterView | None = Field(description="Set for kind=cl")
    lint: LintView | None = Field(description="null: saved without an ATS lint report")
    photo_id: int | None = Field(description="Photo in the CV header; null: none")


class DocumentList(BaseModel):
    documents: list[DocumentView] = Field(description="Newest first")


class CeilingView(BaseModel):
    """The most keyword coverage an honest CV for this job can reach: only words a confirmed
    fact backs. It is known before the CV is written."""

    percent: int = Field(
        description="Share of all analysis keywords (a group a | b counts once) a "
        "confirmed fact backs; 90 is needed"
    )
    unbacked: list[str] = Field(
        description="Keywords no confirmed fact backs: gaps, never add them to the CV"
    )
    reaches_target: bool = Field(
        description="False: percent is below 90, warn the user now and name the unbacked "
        "words; a new confirmed fact for them raises it"
    )


class CvBriefView(BaseModel):
    job: JobView
    analysis: AnalysisView | None = Field(
        description="Keywords, must-haves and gaps; null: not analysed yet"
    )
    profile: Profile
    confirmed_facts: list[FactView] = Field(
        description="The only evidence of the user's experience; cite their fact_id"
    )
    rules: str
    previous: DocumentView | None = Field(description="The last saved CV, if any")
    photos: PhotoList = Field(description="Photos to offer the user before save_cv")
    ceiling: CeilingView | None = Field(
        default=None,
        description="null: the analysis has no fact map or keywords (old analysis), "
        "no ceiling can be stated",
    )


class CoverLetterBriefView(BaseModel):
    job: JobView
    analysis: AnalysisView | None = Field(
        description="Must-haves and keywords; null: not analysed yet"
    )
    profile: Profile
    confirmed_facts: list[FactView] = Field(
        description="The only evidence of the user's experience; cite their fact_id"
    )
    rules: str
    cv: DocumentView | None = Field(description="The last CV for this job, if any")
    previous: DocumentView | None = Field(
        description="The last saved cover letter, if any"
    )


def register_document_tools(
    agent: MCPServer,
    use_cases: DocumentUseCases,
    prompts: Prompts,
    pdf_url: Callable[[int], str],
    photo_links: PhotoLinks,
) -> None:
    def view(document: DocumentData) -> DocumentView:
        return document_view(document, pdf_url(document.document_number))

    def optional(document: DocumentData | None) -> DocumentView | None:
        return None if document is None else view(document)

    @agent.tool(
        name="prepare_cv",
        description=prompts.get(PromptKey.MCP_TOOL_PREPARE_CV),
        annotations=READ,
    )
    async def prepare_cv(job_id: int) -> CvBriefView:
        try:
            brief = await use_cases.prepare_cv(current_actor(), job_id)
        except DomainError as error:
            raise ToolError(error.message) from error
        return CvBriefView(
            job=job_view(brief.job),
            analysis=None if brief.analysis is None else analysis_view(brief.analysis),
            profile=profile_view(brief.profile),
            confirmed_facts=[fact_view(fact) for fact in brief.confirmed_facts],
            rules=brief.rules,
            previous=optional(brief.previous),
            photos=photo_list(brief.photos, photo_links),
            ceiling=None
            if brief.ceiling is None
            else CeilingView(
                percent=brief.ceiling.percent,
                unbacked=list(brief.ceiling.unbacked),
                reaches_target=brief.ceiling.reaches_target,
            ),
        )

    @agent.tool(
        name="save_cv",
        description=prompts.get(PromptKey.MCP_TOOL_SAVE_CV),
        annotations=CREATE,
    )
    async def save_cv(
        job_id: int,
        cv: CvIn,
        photo_id: Annotated[
            int | None,
            Field(
                description="Header photo the user picked (list_photos); null: no photo"
            ),
        ] = None,
    ) -> DocumentView:
        try:
            saved = await use_cases.save_cv(
                current_actor(), job_id, _cv_data(cv), photo_id
            )
        except DomainError as error:
            raise ToolError(error.message) from error
        return view(saved)

    @agent.tool(
        name="check_cv",
        description=prompts.get(PromptKey.MCP_TOOL_CHECK_CV),
        annotations=READ,
    )
    async def check_cv(
        job_id: int,
        cv: CvIn,
        photo_id: Annotated[
            int | None,
            Field(
                description="Header photo the user picked (list_photos); null: no photo"
            ),
        ] = None,
        must_have_facts: Annotated[
            list[MustHaveFactsIn] | None,
            Field(
                description="Optional: for each must_have item of the analysis the "
                "confirmed facts that answer it and whether directly or as an analogue; "
                "the result then says per item covered, analogue or missing"
            ),
        ] = None,
    ) -> CvCheckView:
        try:
            checked = await use_cases.check_cv(
                current_actor(),
                job_id,
                _cv_data(cv),
                photo_id,
                [
                    MustHaveFactsData(
                        item=entry.item, fact_ids=entry.fact_ids, kind=entry.kind
                    )
                    for entry in must_have_facts or ()
                ],
            )
        except DomainError as error:
            raise ToolError(error.message) from error
        return _cv_check_view(checked)

    @agent.tool(
        name="prepare_cover_letter",
        description=prompts.get(PromptKey.MCP_TOOL_PREPARE_COVER_LETTER),
        annotations=READ,
    )
    async def prepare_cover_letter(job_id: int) -> CoverLetterBriefView:
        try:
            brief = await use_cases.prepare_cover_letter(current_actor(), job_id)
        except DomainError as error:
            raise ToolError(error.message) from error
        return _letter_brief(brief, optional)

    @agent.tool(
        name="save_cover_letter",
        description=prompts.get(PromptKey.MCP_TOOL_SAVE_COVER_LETTER),
        annotations=CREATE,
    )
    async def save_cover_letter(
        job_id: int,
        text: Annotated[str, Field(description=LETTER_TEXT)],
        fact_ids: Annotated[
            list[int], Field(description="All confirmed facts the letter uses")
        ],
    ) -> DocumentView:
        data = CoverLetterData(text=text, fact_ids=fact_ids)
        try:
            saved = await use_cases.save_cover_letter(current_actor(), job_id, data)
        except DomainError as error:
            raise ToolError(error.message) from error
        return view(saved)

    @agent.tool(
        name="check_cover_letter",
        description=prompts.get(PromptKey.MCP_TOOL_CHECK_COVER_LETTER),
        annotations=READ,
    )
    async def check_cover_letter(
        job_id: int,
        text: Annotated[str, Field(description=LETTER_TEXT)],
        fact_ids: Annotated[
            list[int], Field(description="All confirmed facts the letter uses")
        ],
    ) -> CheckView:
        data = CoverLetterData(text=text, fact_ids=fact_ids)
        try:
            checked = await use_cases.check_cover_letter(current_actor(), job_id, data)
        except DomainError as error:
            raise ToolError(error.message) from error
        return _check_view(checked)

    @agent.tool(
        name="list_documents",
        description=prompts.get(PromptKey.MCP_TOOL_LIST_DOCUMENTS),
        annotations=READ,
    )
    async def list_documents(job_id: int) -> DocumentList:
        found = await use_cases.list_documents(current_actor(), job_id)
        return DocumentList(documents=[view(document) for document in found])


def _letter_brief(
    brief: CoverLetterBriefData,
    optional: Callable[[DocumentData | None], DocumentView | None],
) -> CoverLetterBriefView:
    return CoverLetterBriefView(
        job=job_view(brief.job),
        analysis=None if brief.analysis is None else analysis_view(brief.analysis),
        profile=profile_view(brief.profile),
        confirmed_facts=[fact_view(fact) for fact in brief.confirmed_facts],
        rules=brief.rules,
        cv=optional(brief.cv),
        previous=optional(brief.previous),
    )


def document_view(document: DocumentData, pdf_url: str) -> DocumentView:
    content = document.content
    return DocumentView(
        document_id=document.document_number,
        job_id=document.job_number,
        kind=document.kind.value,
        version=document.version,
        created=local_day(document.created_at),
        pdf_url=pdf_url,
        cv=_cv_in(content) if isinstance(content, CvData) else None,
        cover_letter=_letter_view(content)
        if isinstance(content, CoverLetterData)
        else None,
        lint=None if document.lint is None else _lint_view(document.lint),
        photo_id=document.photo_number,
    )


def _check_view(checked: CheckData) -> CheckView:
    keywords = checked.keywords
    return CheckView(
        passed=checked.passed,
        issues=[
            LintIssueView(code=issue.code.value, message=issue.message)
            for issue in checked.issues
        ],
        keywords=None
        if keywords is None
        else KeywordsView(
            covered=list(keywords.covered),
            missing=list(keywords.missing),
            percent=keywords.percent,
        ),
    )


def _cv_check_view(checked: CheckData) -> CvCheckView:
    gate = checked.gate
    must_have = checked.must_have_coverage
    return CvCheckView(
        **_check_view(checked).model_dump(),
        gate=None
        if gate is None
        else GateView(
            status=gate.status,
            evidence_percent=gate.evidence_percent,
            evidence_missing=list(gate.evidence_missing),
            coverage_percent=gate.coverage_percent,
        ),
        must_have_coverage=None
        if must_have is None
        else MustHaveCoverageView(
            items=[
                MustHaveItemView(
                    item=item.item,
                    status=item.status.value,
                    fact_ids=list(item.fact_ids),
                    reason=item.reason,
                )
                for item in must_have.items
            ],
            unknown=list(must_have.unknown),
        ),
    )


def _lint_view(report: LintData) -> LintView:
    keywords = report.keywords
    return LintView(
        passed=report.passed,
        pages=report.pages,
        issues=[
            LintIssueView(code=issue.code.value, message=issue.message)
            for issue in report.issues
        ],
        keywords_covered=None if keywords is None else list(keywords.covered),
        keywords_missing=None if keywords is None else list(keywords.missing),
        keyword_coverage_percent=None if keywords is None else keywords.percent,
    )


def _letter_view(letter: CoverLetterData) -> CoverLetterView:
    return CoverLetterView(text=letter.text, fact_ids=list(letter.fact_ids))


def _claim_data(claim: ClaimIn) -> ClaimData:
    return ClaimData(text=claim.text, fact_ids=claim.fact_ids)


def _optional_data(claim: ClaimIn | None) -> ClaimData | None:
    return None if claim is None else _claim_data(claim)


def _cv_data(cv: CvIn) -> CvData:
    return CvData(
        headline=_claim_data(cv.headline),
        summary=_claim_data(cv.summary),
        sections=[
            CvSectionData(
                name=section.name,
                entries=[
                    CvEntryData(
                        heading=_claim_data(entry.heading),
                        bullets=[_claim_data(bullet) for bullet in entry.bullets],
                        meta=_optional_data(entry.meta),
                        subtitle=_optional_data(entry.subtitle),
                    )
                    for entry in section.entries
                ],
            )
            for section in cv.sections
        ],
    )


def _claim_in(claim: ClaimData) -> ClaimIn:
    return ClaimIn(text=claim.text, fact_ids=list(claim.fact_ids))


def _optional_in(claim: ClaimData | None) -> ClaimIn | None:
    return None if claim is None else _claim_in(claim)


def _cv_in(cv: CvData) -> CvIn:
    return CvIn(
        headline=_claim_in(cv.headline),
        summary=_claim_in(cv.summary),
        sections=[
            CvSectionIn(
                name=section.name,
                entries=[
                    CvEntryIn(
                        heading=_claim_in(entry.heading),
                        meta=_optional_in(entry.meta),
                        subtitle=_optional_in(entry.subtitle),
                        bullets=[_claim_in(bullet) for bullet in entry.bullets],
                    )
                    for entry in section.entries
                ],
            )
            for section in cv.sections
        ],
    )
