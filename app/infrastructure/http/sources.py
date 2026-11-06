"""HTTP керування джерелами для вебу: список компаній і RSS-стрічок з останнім прогоном, додати
компанію (з пробним запитом до ATS) і стрічку, вимкнути, увімкнути, видалити; «оновити зараз» (ліміт
2 запити за 30 хв, 429 з Retry-After); вакансії, що вже не проходять фільтр профілю, і їх приховування.

Правила введення й тексти помилок — у домені (`parse_company`, `parse_feed`), не в pydantic.
Усе, що не належить користувачеві, — 404, як і неіснуюче."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict

from application.contracts.actor import Actor
from application.contracts.sources import (
    CompanyInput,
    FeedInput,
    RefreshState,
    SourcesOverview,
)
from application.sources.filtered import FilteredJobUseCases
from application.sources.manage import SourceManageUseCases
from application.sources.overview import SourceOverviewUseCases
from domain.sources.filtered import FilteredJob
from domain.sources.manage import CompanyRow, FeedRow
from domain.sources.refresh_requests import MANUAL_REFRESH_LIMIT
from domain.sources.run import SourceRun
from infrastructure.http.auth import HttpAuth

PlatformName = Literal["greenhouse", "ashby", "lever"]
FeedSourceName = Literal["dou", "djinni"]
FailureName = Literal[
    "timeout",
    "not_found",
    "rate_limited",
    "unavailable",
    "rejected",
    "invalid",
    "unsupported",
]


class CompanyBody(BaseModel):
    """Сирі значення: платформу, слаг і назву перевіряє домен."""

    model_config = ConfigDict(extra="forbid")

    platform: str
    slug: str
    name: str = ""


class FeedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    query: str


class EnabledBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class DismissBody(BaseModel):
    """Номери вакансій, які користувач бачив у списку «уже не проходять фільтр»."""

    model_config = ConfigDict(extra="forbid")

    numbers: list[int]


class LastRunModel(BaseModel):
    ran_at: datetime
    found: int
    imported: int
    filtered: int
    duplicate: int
    completed: int
    # Код збою читання; null — прогін вдався.
    error: FailureName | None


class CompanyModel(BaseModel):
    id: str
    platform: PlatformName
    slug: str
    name: str
    enabled: bool
    # null — прогону ще не було.
    last_run: LastRunModel | None


class FeedModel(BaseModel):
    id: str
    source: FeedSourceName
    query: str
    enabled: bool
    last_run: LastRunModel | None


class RefreshModel(BaseModel):
    limit: int
    remaining: int
    # Коли звільниться наступний запит; null — запити є.
    next_at: datetime | None
    # Коли джерела користувача востаннє оновлювались; null — прогонів ще не було.
    last_run_at: datetime | None


class SourcesModel(BaseModel):
    companies: list[CompanyModel]
    feeds: list[FeedModel]
    refresh: RefreshModel
    filtered_out_count: int


class FilteredJobModel(BaseModel):
    number: int
    title: str | None
    company: str | None
    reason: Literal["title", "excluded", "format", "location"]


class DismissedModel(BaseModel):
    dismissed: int


def last_run_model(run: SourceRun | None) -> LastRunModel | None:
    if run is None:
        return None
    return LastRunModel(
        ran_at=run.ran_at,
        found=run.summary.found,
        imported=run.summary.imported,
        filtered=run.summary.filtered,
        duplicate=run.summary.duplicate,
        completed=run.summary.completed,
        error=None if run.error is None else run.error.value,
    )


def company_model(row: CompanyRow) -> CompanyModel:
    company = row.company
    return CompanyModel(
        id=str(company.id),
        platform=company.platform.value,
        slug=company.slug,
        name=company.name,
        enabled=company.enabled,
        last_run=last_run_model(row.run),
    )


def feed_model(row: FeedRow) -> FeedModel:
    feed = row.feed
    return FeedModel(
        id=str(feed.id),
        source=feed.source.value,
        query=feed.query,
        enabled=feed.enabled,
        last_run=last_run_model(row.run),
    )


def refresh_model(state: RefreshState) -> RefreshModel:
    return RefreshModel(
        limit=MANUAL_REFRESH_LIMIT,
        remaining=state.remaining,
        next_at=state.next_at,
        last_run_at=state.last_run_at,
    )


def sources_model(found: SourcesOverview) -> SourcesModel:
    return SourcesModel(
        companies=[company_model(row) for row in found.companies],
        feeds=[feed_model(row) for row in found.feeds],
        refresh=refresh_model(found.refresh),
        filtered_out_count=len(found.filtered),
    )


def filtered_model(item: FilteredJob) -> FilteredJobModel:
    # `empty` сюди не доходить: вакансія без тексту — не справа профілю (domain.sources.filtered).
    return FilteredJobModel(
        number=item.number,
        title=item.title,
        company=item.company,
        reason=item.reason.value,
    )


def sources_router(
    sources: SourceManageUseCases,
    overview: SourceOverviewUseCases,
    filtered: FilteredJobUseCases,
    auth: HttpAuth,
) -> APIRouter:
    router = APIRouter(prefix="/sources", tags=["sources"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    def private(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    @router.get("")
    async def listing(actor: Caller, response: Response) -> SourcesModel:
        private(response)
        return sources_model(await overview.overview(actor))

    @router.post("/refresh", status_code=202)
    async def refresh(actor: Caller, response: Response) -> RefreshModel:
        private(response)
        return refresh_model(await overview.request_refresh(actor))

    @router.get("/filtered")
    async def filtered_jobs(
        actor: Caller, response: Response
    ) -> list[FilteredJobModel]:
        private(response)
        return [filtered_model(item) for item in await filtered.list_filtered(actor)]

    @router.post("/filtered/dismiss")
    async def dismiss_filtered(
        body: DismissBody, actor: Caller, response: Response
    ) -> DismissedModel:
        private(response)
        return DismissedModel(
            dismissed=await filtered.dismiss_filtered(actor, body.numbers)
        )

    @router.post("/companies", status_code=201)
    async def add_company(
        body: CompanyBody, actor: Caller, response: Response
    ) -> CompanyModel:
        private(response)
        data = CompanyInput(platform=body.platform, slug=body.slug, name=body.name)
        return company_model(await sources.add_company(actor, data))

    @router.post("/feeds", status_code=201)
    async def add_feed(body: FeedBody, actor: Caller, response: Response) -> FeedModel:
        private(response)
        data = FeedInput(source=body.source, query=body.query)
        return feed_model(await sources.add_feed(actor, data))

    @router.patch("/companies/{source_id}")
    async def set_company_enabled(
        source_id: str, body: EnabledBody, actor: Caller, response: Response
    ) -> CompanyModel:
        private(response)
        return company_model(
            await sources.set_company_enabled(actor, source_id, body.enabled)
        )

    @router.patch("/feeds/{source_id}")
    async def set_feed_enabled(
        source_id: str, body: EnabledBody, actor: Caller, response: Response
    ) -> FeedModel:
        private(response)
        return feed_model(
            await sources.set_feed_enabled(actor, source_id, body.enabled)
        )

    @router.delete("/companies/{source_id}", status_code=204)
    async def remove_company(source_id: str, actor: Caller) -> Response:
        await sources.remove_company(actor, source_id)
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @router.delete("/feeds/{source_id}", status_code=204)
    async def remove_feed(source_id: str, actor: Caller) -> Response:
        await sources.remove_feed(actor, source_id)
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    return router
