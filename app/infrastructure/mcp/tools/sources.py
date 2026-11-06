"""Тули джерел `get_sources` і `refresh_sources`: компанії й стрічки користувача зі станом прогонів,
ліміт «оновити зараз», вакансії, що вже не проходять фільтр профілю, і запит на оновлення.

Назви, поля відповіді й типи — як у v1 (контракт-тест зі знімком схеми). Агент у мережу ATS не ходить:
запит лише ставиться в чергу, прогін запускає сервер. Список джерел змінює користувач у вебі. Опис
тулів — у каталозі промптів.
"""

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.contracts.sources import SourcesOverview
from application.ports.prompts import PromptKey, Prompts
from application.sources.overview import SourceOverviewUseCases
from domain.shared.errors import DomainError
from domain.shared.local_time import local_minute
from domain.sources.run import SourceRun
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import CREATE, READ

REFRESH_QUEUED = "Refresh requested: the server starts it within about a minute."


class RunView(BaseModel):
    ran_at: str = Field(description="YYYY-MM-DD HH:MM, Europe/Madrid time")
    found: int = Field(description="Postings the source returned")
    imported: int = Field(description="New jobs saved (with full text)")
    filtered: int = Field(description="Skipped by the user's profile filters")
    duplicate: int = Field(
        description="Already saved (same URL, text, or company + title)"
    )
    completed: int = Field(
        description="LinkedIn-alert jobs that had no text and received it from this source"
    )
    error: str | None = Field(
        description="null: the run succeeded. Otherwise a code: timeout, not_found, "
        "rate_limited, unavailable, rejected, invalid, unsupported"
    )


class CompanyView(BaseModel):
    name: str
    platform: str = Field(description="greenhouse, ashby or lever")
    slug: str
    enabled: bool
    last_run: RunView | None = Field(description="null: never refreshed")


class FeedView(BaseModel):
    source: str = Field(description="dou or djinni")
    query: str = Field(
        description="The feed's query string, e.g. category=Python&remote"
    )
    enabled: bool
    last_run: RunView | None = Field(description="null: never refreshed")


class FilteredJobView(BaseModel):
    job_id: int
    title: str | None
    company: str | None
    reason: str = Field(
        description="Which filter it fails now: title (no wanted word), excluded (excluded word in the title), "
        "format (work mode), location"
    )


class FilteredOutView(BaseModel):
    count: int
    jobs: list[FilteredJobView]


class SourcesView(BaseModel):
    companies: list[CompanyView]
    feeds: list[FeedView]
    refresh_requests_left: int = Field(
        description="How many refresh_sources calls are allowed now (limit per 30 minutes)"
    )
    next_refresh_at: str | None = Field(
        description="YYYY-MM-DD HH:MM Europe/Madrid time when the next refresh can be requested; null: now"
    )
    filtered_out: FilteredOutView = Field(
        description="Saved jobs the user's CURRENT profile filters would no longer take (not hidden, "
        "analysed or applied to). Show the list; dismiss_jobs only after they say yes"
    )
    settings_url: str = Field(
        description="The user's sources page: they add and remove companies and feeds there"
    )


class RefreshRequested(BaseModel):
    requested: bool = True
    refresh_requests_left: int
    message: str


def _run_view(run: SourceRun | None) -> RunView | None:
    if run is None:
        return None
    return RunView(
        ran_at=local_minute(run.ran_at),
        found=run.summary.found,
        imported=run.summary.imported,
        filtered=run.summary.filtered,
        duplicate=run.summary.duplicate,
        completed=run.summary.completed,
        error=None if run.error is None else run.error.value,
    )


def sources_view(overview: SourcesOverview, web_url: str) -> SourcesView:
    next_at = overview.refresh.next_at
    return SourcesView(
        companies=[
            CompanyView(
                name=row.company.name,
                platform=row.company.platform.value,
                slug=row.company.slug,
                enabled=row.company.enabled,
                last_run=_run_view(row.run),
            )
            for row in overview.companies
        ],
        feeds=[
            FeedView(
                source=row.feed.source.value,
                query=row.feed.query,
                enabled=row.feed.enabled,
                last_run=_run_view(row.run),
            )
            for row in overview.feeds
        ],
        refresh_requests_left=overview.refresh.remaining,
        next_refresh_at=None if next_at is None else local_minute(next_at),
        filtered_out=FilteredOutView(
            count=len(overview.filtered),
            jobs=[
                FilteredJobView(
                    job_id=job.number,
                    title=job.title,
                    company=job.company,
                    reason=job.reason.value,
                )
                for job in overview.filtered
            ],
        ),
        settings_url=f"{web_url.rstrip('/')}/sources",
    )


def register_source_tools(
    agent: MCPServer,
    overview: SourceOverviewUseCases,
    prompts: Prompts,
    web_url: str,
) -> None:
    @agent.tool(
        name="get_sources",
        description=prompts.get(PromptKey.MCP_TOOL_GET_SOURCES),
        annotations=READ,
    )
    async def get_sources() -> SourcesView:
        try:
            found = await overview.overview(current_actor())
        except DomainError as error:
            raise ToolError(error.message) from error
        return sources_view(found, web_url)

    @agent.tool(
        name="refresh_sources",
        description=prompts.get(PromptKey.MCP_TOOL_REFRESH_SOURCES),
        annotations=CREATE,
    )
    async def refresh_sources() -> RefreshRequested:
        try:
            state = await overview.request_refresh(current_actor())
        except DomainError as error:
            raise ToolError(error.message) from error
        return RefreshRequested(
            refresh_requests_left=state.remaining, message=REFRESH_QUEUED
        )
