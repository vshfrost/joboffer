"""Бізнес-тули агента: composition root передає кожній області її use cases й промпти."""

from mcp.server.mcpserver import MCPServer

from bootstrap.container import Container
from infrastructure.mcp.tools.analysis import register_analysis_tools
from infrastructure.mcp.tools.applications import register_application_tools
from infrastructure.mcp.tools.document_downloads import (
    register_document_download_tool,
)
from infrastructure.mcp.tools.documents import register_document_tools
from infrastructure.mcp.tools.facts import register_fact_tools
from infrastructure.mcp.tools.funnel import register_funnel_tools
from infrastructure.mcp.tools.gaps import register_gap_tools
from infrastructure.mcp.tools.interview import register_interview_tools
from infrastructure.mcp.tools.jobs import register_job_tools
from infrastructure.mcp.tools.mail import register_mail_tools
from infrastructure.mcp.tools.photos import PhotoLinks, register_photo_tools
from infrastructure.mcp.tools.prep import register_prep_tools
from infrastructure.mcp.tools.profile import register_profile_tools
from infrastructure.mcp.tools.quiz import register_quiz_tools
from infrastructure.mcp.tools.replies import register_reply_tools
from infrastructure.mcp.tools.scenarios import register_scenario_tools
from infrastructure.mcp.tools.sources import register_source_tools
from infrastructure.mcp.tools.triage import register_triage_tools


def register_tools(agent: MCPServer, container: Container) -> None:
    register_profile_tools(agent, container.profile, container.prompts)
    register_job_tools(agent, container.jobs, container.prompts)
    register_application_tools(agent, container.applications, container.prompts)
    register_funnel_tools(agent, container.applications, container.prompts)
    register_mail_tools(
        agent,
        container.mail,
        container.prompts,
        container.settings.web_public_url,
    )
    register_reply_tools(agent, container.replies, container.prompts)
    register_source_tools(
        agent,
        container.source_overview,
        container.prompts,
        container.settings.web_public_url,
    )
    register_fact_tools(agent, container.facts, container.prompts)
    register_triage_tools(agent, container.triage, container.prompts)
    register_analysis_tools(agent, container.analysis, container.prompts)
    register_gap_tools(agent, container.analysis, container.prompts)
    register_scenario_tools(agent, container.scenarios, container.prompts)
    register_prep_tools(agent, container.prep, container.prompts)
    register_quiz_tools(agent, container.quiz, container.prompts)
    register_interview_tools(agent, container.interview_kits, container.prompts)
    web = container.settings.web_public_url.rstrip("/")
    links = PhotoLinks(
        lambda number: f"{web}/api/photos/{number}.jpg", f"{web}/profile/photos"
    )
    register_document_tools(
        agent,
        container.documents,
        container.prompts,
        lambda number: f"{web}/api/documents/{number}/pdf",
        links,
    )
    register_document_download_tool(
        agent,
        container.document_downloads,
        container.prompts,
        lambda token: f"{web}/api/documents/download/{token}",
    )
    register_photo_tools(
        agent, container.photos, container.prompts, links.preview_url, links.upload_url
    )
