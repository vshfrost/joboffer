"""HTTP вакансій: список, деталі, додавання, «Не цікаво» / «Повернути».

`job_id` у URL і відповідях — номер вакансії в межах користувача (ціле, з 1); внутрішній UUID
назовні не виходить. Поля тіл — рядки: правила й тексти помилок (v1) у домені, не в pydantic.
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict

from application.contracts.actor import Actor
from application.contracts.jobs import (
    AddedJob,
    AddOutcome,
    JobData,
    JobInput,
    JobSearchInput,
    JobSummaryData,
)
from application.jobs.use_cases import JobUseCases
from domain.jobs.search import DEFAULT_LIMIT
from infrastructure.http.applications import ApplicationStatusName
from infrastructure.http.auth import HttpAuth


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NewJobModel(_Body):
    text: str = ""
    url: str = ""
    title: str = ""
    company: str = ""


class DismissModel(_Body):
    job_ids: list[int] = []
    reason: str = ""


class AddedJobModel(BaseModel):
    job_id: int
    duplicate: bool
    outcome: AddOutcome


TriageVerdictName = Literal["skip", "maybe", "analyse"]
TriageSourceName = Literal["agent", "rules"]
WorkModeName = Literal["remote", "hybrid", "onsite"]


class TriageModel(BaseModel):
    score: int
    verdict: TriageVerdictName
    reason: str
    triaged_at: datetime
    source: TriageSourceName


class JobSummaryModel(BaseModel):
    job_id: int
    source: str
    url: str | None
    title: str | None
    company: str | None
    created_at: datetime
    needs_text: bool
    dismissed: bool
    # Повний аналіз: порожньо — вакансію ще не аналізовано.
    score: int | None
    filters_passed: bool | None
    work_mode: WorkModeName | None
    # Швидкий тріаж: порожньо — вакансію ще не тріажовано.
    triage_score: int | None
    triage_verdict: TriageVerdictName | None
    triage_reason: str | None
    # Статус подачі; порожньо — на вакансію не подавались.
    status: ApplicationStatusName | None
    # Вакансія з джерела (`ats:` / `rss:`), яку ще не відкривали.
    is_new: bool


class JobCountsModel(BaseModel):
    """Лічильники табів: не залежать від фільтрів запиту й від ліміту списку."""

    # Скільки вакансій у табі «У процесі».
    in_progress: int
    # Скільки вакансій мають нерозібраний лист до активної подачі (лічильник на «Подано»).
    applied_unreviewed: int
    # Є не схована вакансія без тексту (бейдж «!» на «Потрібен текст»).
    needs_text: bool


class JobListModel(BaseModel):
    items: list[JobSummaryModel]
    # Різні джерела вакансій користувача — для фільтра за джерелом.
    sources: list[str]
    counts: JobCountsModel


class JobModel(BaseModel):
    job_id: int
    source: str
    url: str | None
    title: str | None
    company: str | None
    location: str | None
    text: str | None
    created_at: datetime
    needs_text: bool
    dismissed_at: datetime | None
    dismiss_reason: str | None
    # Коли вакансію вперше відкрили в деталях.
    opened_at: datetime | None
    is_new: bool
    triage: TriageModel | None


def _summary(item: JobSummaryData) -> JobSummaryModel:
    return JobSummaryModel(
        job_id=item.job_number,
        source=item.source,
        url=item.url,
        title=item.title,
        company=item.company,
        created_at=item.created_at,
        needs_text=item.needs_text,
        dismissed=item.dismissed,
        score=item.score,
        filters_passed=item.filters_passed,
        work_mode=None if item.work_mode is None else item.work_mode.value,
        triage_score=item.triage_score,
        triage_verdict=None
        if item.triage_verdict is None
        else item.triage_verdict.value,
        triage_reason=item.triage_reason,
        status=None if item.status is None else item.status.value,
        is_new=item.is_new,
    )


def _job(job: JobData) -> JobModel:
    return JobModel(
        job_id=job.job_number,
        source=job.source,
        url=job.url,
        title=job.title,
        company=job.company,
        location=job.location,
        text=job.text,
        created_at=job.created_at,
        needs_text=job.needs_text,
        dismissed_at=job.dismissed_at,
        dismiss_reason=job.dismiss_reason,
        opened_at=job.opened_at,
        is_new=job.is_new,
        triage=None
        if job.triage is None
        else TriageModel(
            score=job.triage.score,
            verdict=job.triage.verdict.value,
            reason=job.triage.reason,
            triaged_at=job.triage.triaged_at,
            source=job.triage.source.value,
        ),
    )


def _added(added: AddedJob) -> AddedJobModel:
    return AddedJobModel(
        job_id=added.job_number, duplicate=added.duplicate, outcome=added.outcome
    )


def jobs_router(jobs: JobUseCases, auth: HttpAuth) -> APIRouter:
    router = APIRouter(prefix="/jobs", tags=["jobs"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    def private(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    @router.get("")
    async def listing(  # noqa: PLR0913, PLR0917 — по параметру на фільтр
        actor: Caller,
        response: Response,
        query: str = "",
        days: str = "",
        source: str = "",
        needs_text: bool = False,
        work_mode: str = "",
        triage_verdict: str = "",
        status: str = "",
        stage: str = "",
        dismissed: bool = False,
        limit: int = DEFAULT_LIMIT,
    ) -> JobListModel:
        private(response)
        found = await jobs.list_jobs(
            actor,
            JobSearchInput(
                query=query,
                days=days,
                source=source,
                needs_text=needs_text,
                work_mode=work_mode,
                triage_verdict=triage_verdict,
                status=status,
                stage=stage,
                # Веб не показує відмов у жодному табі; MCP `list_jobs` їх лишає.
                hide_rejected=True,
                dismissed=dismissed,
                limit=limit,
            ),
        )
        counts = await jobs.tab_counts(actor)
        return JobListModel(
            items=[_summary(item) for item in found],
            sources=await jobs.job_sources(actor),
            counts=JobCountsModel(
                in_progress=counts.in_progress,
                applied_unreviewed=counts.applied_unreviewed,
                needs_text=counts.needs_text,
            ),
        )

    @router.post("", status_code=201)
    async def add(
        body: NewJobModel, actor: Caller, response: Response
    ) -> AddedJobModel:
        private(response)
        added = await jobs.add_job(
            actor,
            JobInput(
                text=body.text, url=body.url, title=body.title, company=body.company
            ),
        )
        if added.outcome is not AddOutcome.CREATED:
            response.status_code = 200
        return _added(added)

    @router.post("/dismiss", status_code=204)
    async def dismiss(body: DismissModel, actor: Caller) -> Response:
        await jobs.dismiss_jobs(actor, body.job_ids, body.reason)
        return Response(status_code=204)

    @router.get("/{job_id}")
    async def details(job_id: int, actor: Caller, response: Response) -> JobModel:
        private(response)
        return _job(await jobs.open_job(actor, job_id))

    @router.post("/{job_id}/restore", status_code=204)
    async def restore(job_id: int, actor: Caller) -> Response:
        await jobs.restore_job(actor, job_id)
        return Response(status_code=204)

    return router
