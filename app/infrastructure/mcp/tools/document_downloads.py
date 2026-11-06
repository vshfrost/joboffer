"""Тул `get_document_download`: одноразове посилання, за яким shell агента качає PDF документа.

Розширення браузера (file_upload) прикріплює лише локальний файл, а `pdf_url` з `list_documents`
відкривається тільки з сесією веба. Посилання з цього тула працює без сесії: один раз і 10 хвилин.
"""

from collections.abc import Callable
from datetime import datetime

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.documents.downloads import DocumentDownloads
from application.ports.prompts import PromptKey, Prompts
from domain.shared.errors import DomainError
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import CREATE


class DocumentDownload(BaseModel):
    url: str = Field(description="Single-use link; no session needed")
    file_name: str = Field(description="Name to give the downloaded file")
    expires_at: datetime = Field(description="The link stops working at this moment")


def register_document_download_tool(
    agent: MCPServer,
    downloads: DocumentDownloads,
    prompts: Prompts,
    download_url: Callable[[str], str],
) -> None:
    @agent.tool(
        name="get_document_download",
        description=prompts.get(PromptKey.MCP_TOOL_GET_DOCUMENT_DOWNLOAD),
        annotations=CREATE,
    )
    async def get_document_download(document_id: int) -> DocumentDownload:
        try:
            link = await downloads.create_link(current_actor(), document_id)
        except DomainError as error:
            raise ToolError(error.message) from error
        return DocumentDownload(
            url=download_url(link.token),
            file_name=link.file_name,
            expires_at=link.expires_at,
        )
