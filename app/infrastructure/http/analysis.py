"""HTTP аналізу вакансії: збережений аналіз зі знаком застарілості.

`job_id` у URL — номер вакансії в межах користувача (ціле, з 1). Аналіз пише лише Claude
через MCP (`save_analysis`); у вебі його читають. Вакансії чи аналізу нема — 404 (однаково).
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from application.analysis.use_cases import AnalysisUseCases
from application.contracts.actor import Actor
from application.contracts.analysis import AnalysisData, GapData
from infrastructure.http.auth import HttpAuth

SeniorityName = Literal["junior", "middle", "senior", "lead", "principal"]
WorkModeName = Literal["remote", "hybrid", "onsite"]
GapStatus = Literal["open", "closed", "no_experience"]


class GapModel(BaseModel):
    number: int
    gap: str
    question: str | None
    status: GapStatus
    fact_ids: list[int]


class AnalysisModel(BaseModel):
    job_id: int
    score: int
    summary: str
    must_have: list[str]
    nice_to_have: list[str]
    keywords: list[str]
    candidate_asks: list[str]
    seniority: SeniorityName | None
    work_mode: WorkModeName | None
    location: str | None
    languages: list[str]
    salary_min_eur: int | None
    salary_max_eur: int | None
    relocation: bool | None
    reasons: list[str]
    gaps: list[GapModel]
    # Знімок жорстких фільтрів профілю на момент збереження аналізу.
    filters_passed: bool
    flags: list[str]
    updated_at: datetime
    # З якого моменту профіль змінено після аналізу (ціль, локації чи правила); null — актуальний.
    stale_since: datetime | None


def _gap(gap: GapData) -> GapModel:
    """Без відповіді прогалина відкрита; «є досвід» закриває її фактами, «нема досвіду» — ні."""
    answer = gap.answer
    if answer is None:
        status: GapStatus = "open"
    else:
        status = "closed" if answer.has_experience else "no_experience"
    return GapModel(
        number=gap.number,
        gap=gap.gap,
        question=gap.question,
        status=status,
        fact_ids=[] if answer is None else list(answer.fact_numbers),
    )


def _model(data: AnalysisData) -> AnalysisModel:
    return AnalysisModel(
        job_id=data.job_number,
        score=data.score,
        summary=data.summary,
        must_have=list(data.must_have),
        nice_to_have=list(data.nice_to_have),
        keywords=list(data.keywords),
        candidate_asks=list(data.candidate_asks),
        seniority=None if data.seniority is None else data.seniority.value,
        work_mode=None if data.work_mode is None else data.work_mode.value,
        location=data.location,
        languages=list(data.languages),
        salary_min_eur=data.salary_min_eur,
        salary_max_eur=data.salary_max_eur,
        relocation=data.relocation,
        reasons=list(data.reasons),
        gaps=[_gap(g) for g in data.gaps],
        filters_passed=data.filters_passed,
        flags=list(data.flags),
        updated_at=data.updated_at,
        stale_since=data.stale_since,
    )


def analysis_router(analysis: AnalysisUseCases, auth: HttpAuth) -> APIRouter:
    router = APIRouter(prefix="/jobs", tags=["analysis"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    @router.get("/{job_id}/analysis")
    async def details(job_id: int, actor: Caller, response: Response) -> AnalysisModel:
        response.headers["Cache-Control"] = "no-store"
        return _model(await analysis.get_analysis(actor, job_id))

    return router
