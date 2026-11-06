"""Тули подач: `mark_applied`, `set_application_status`.

Назви, параметри, поля відповідей і enum-и — як у v1. Описи тулів — у каталозі промптів;
решту (тексти помилок) перевіряє домен.
"""

from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.applications.use_cases import ApplicationUseCases
from application.contracts.applications import ApplicationData, ApplicationInput
from application.ports.prompts import PromptKey, Prompts
from domain.shared.errors import DomainError
from domain.shared.local_time import local_day
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import WRITE

ApplicationStatusName = Literal[
    "applied", "replied", "interview", "offer", "rejected", "withdrawn"
]
ChannelName = Literal["email", "ats", "linkedin", "referral"]
AtsName = Literal[
    "greenhouse", "lever", "ashby", "workable", "smartrecruiters", "other"
]


class ApplicationIn(BaseModel):
    channel: ChannelName
    applied_on: str = Field(
        default="", description="YYYY-MM-DD; empty: today (Europe/Madrid)"
    )
    ats: AtsName | None = Field(
        default=None, description="ATS platform the application went through"
    )
    company_domains: list[str] = Field(
        default_factory=list,
        description="The company's own email domains, e.g. acme.com (not the ATS's)",
    )
    company_emails: list[str] = Field(
        default_factory=list, description="Recruiters' addresses the user knows"
    )


class ApplicationView(BaseModel):
    job_id: int
    status: ApplicationStatusName
    applied_on: str = Field(description="YYYY-MM-DD")
    channel: ChannelName
    ats: AtsName | None
    company_domains: list[str] = Field(
        description="The company's email domains: replies from them match this job"
    )
    company_emails: list[str]
    status_changed: str = Field(description="YYYY-MM-DD")


def application_view(data: ApplicationData) -> ApplicationView:
    return ApplicationView(
        job_id=data.job_number,
        status=data.status.value,
        applied_on=data.applied_on.isoformat(),
        channel=data.channel.value,
        ats=None if data.ats is None else data.ats.value,
        company_domains=list(data.company_domains),
        company_emails=list(data.company_emails),
        status_changed=local_day(data.status_changed_at),
    )


def register_application_tools(
    agent: MCPServer, applications: ApplicationUseCases, prompts: Prompts
) -> None:
    @agent.tool(
        name="mark_applied",
        description=prompts.get(PromptKey.MCP_TOOL_MARK_APPLIED),
        annotations=WRITE,
    )
    async def mark_applied(job_id: int, application: ApplicationIn) -> ApplicationView:
        data = ApplicationInput(
            channel=application.channel,
            applied_on=application.applied_on,
            ats=application.ats or "",
            company_domains=application.company_domains,
            company_emails=application.company_emails,
        )
        try:
            saved = await applications.mark_applied(current_actor(), job_id, data)
        except DomainError as error:
            raise ToolError(error.message) from error
        return application_view(saved)

    @agent.tool(
        name="set_application_status",
        description=prompts.get(PromptKey.MCP_TOOL_SET_APPLICATION_STATUS),
        annotations=WRITE,
    )
    async def set_application_status(
        job_id: int, status: ApplicationStatusName
    ) -> ApplicationView:
        try:
            saved = await applications.set_application_status(
                current_actor(), job_id, status
            )
        except DomainError as error:
            raise ToolError(error.message) from error
        return application_view(saved)
