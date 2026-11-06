"""Тул звіту воронки за версіями CV: `get_cv_funnel`.

Окремий від тулів подач: їхні схеми закріплені знімком v1, а цей тул — нового."""

from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.applications.use_cases import ApplicationUseCases
from application.contracts.applications import CvFunnelData, CvFunnelRowData
from application.ports.prompts import PromptKey, Prompts
from domain.shared.errors import DomainError
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import READ


class CvFunnelRowView(BaseModel):
    cv_number: int | Literal["unknown"] = Field(
        description="Document number of the CV version; unknown: applications made "
        "without a CV or before versions were remembered"
    )
    cv_date: str | None = Field(
        description="YYYY-MM-DD the CV was saved; null: unknown"
    )
    coverage_percent: int | None = Field(
        description="Share of the job's keywords in that CV; null: unknown or the job "
        "was not analysed then"
    )
    applications: int
    replies: int = Field(description="Applications now replied, interview or offer")
    interviews: int = Field(description="Applications now interview or offer")


class CvFunnelView(BaseModel):
    versions: list[CvFunnelRowView] = Field(
        description="By CV version number; unknown last"
    )


def cv_funnel_view(data: CvFunnelData) -> CvFunnelView:
    return CvFunnelView(versions=[_row_view(row) for row in data.rows])


def _row_view(row: CvFunnelRowData) -> CvFunnelRowView:
    return CvFunnelRowView(
        cv_number="unknown" if row.cv_number is None else row.cv_number,
        cv_date=None if row.saved_on is None else row.saved_on.isoformat(),
        coverage_percent=row.coverage_percent,
        applications=row.applications,
        replies=row.replies,
        interviews=row.interviews,
    )


def register_funnel_tools(
    agent: MCPServer, applications: ApplicationUseCases, prompts: Prompts
) -> None:
    @agent.tool(
        name="get_cv_funnel",
        description=prompts.get(PromptKey.MCP_TOOL_GET_CV_FUNNEL),
        annotations=READ,
    )
    async def get_cv_funnel() -> CvFunnelView:
        try:
            funnel = await applications.cv_funnel(current_actor())
        except DomainError as error:
            raise ToolError(error.message) from error
        return cv_funnel_view(funnel)
