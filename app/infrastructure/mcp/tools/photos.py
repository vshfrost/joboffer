"""Тул `list_photos`: фото для шапки CV і те, що запропонувати. Завантажує користувач у вебі:
Claude не може передати в тул байти прикріпленої картинки.

Назва, поля й відповідь — як у v1. Опис — у каталозі промптів; `photo_id` — номер фото в межах
користувача, `preview_url` і `photo_upload_url` — адреси веб-застосунку.
"""

from collections.abc import Callable
from dataclasses import dataclass

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from application.contracts.photos import PhotoLibraryData
from application.photos.use_cases import PhotoUseCases
from application.ports.prompts import PromptKey, Prompts
from domain.shared.local_time import local_day
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import READ


@dataclass(frozen=True, slots=True)
class PhotoLinks:
    """Адреси веб-застосунку у відповідях тулів: перегляд фото і сторінка завантаження."""

    preview_url: Callable[[int], str]
    upload_url: str


class PhotoView(BaseModel):
    photo_id: int
    label: str
    added: str = Field(description="YYYY-MM-DD")
    last_used: str | None = Field(
        description="YYYY-MM-DD of the last CV with it; null: never"
    )
    preview_url: str = Field(description="Opens in the user's browser once signed in")


class PhotoList(BaseModel):
    photos: list[PhotoView] = Field(description="Newest first")
    suggested_photo_id: int | None = Field(
        description="Suggest this one: the last used in a CV, else the newest; null: no photos"
    )
    photo_upload_url: str = Field(description="Where the user uploads photos")


def photo_list(library: PhotoLibraryData, links: PhotoLinks) -> PhotoList:
    return PhotoList(
        photos=[
            PhotoView(
                photo_id=photo.photo_number,
                label=photo.label,
                added=local_day(photo.created_at),
                last_used=None
                if photo.last_used_at is None
                else local_day(photo.last_used_at),
                preview_url=links.preview_url(photo.photo_number),
            )
            for photo in library.photos
        ],
        suggested_photo_id=library.suggested_photo_number,
        photo_upload_url=links.upload_url,
    )


def register_photo_tools(
    agent: MCPServer,
    use_cases: PhotoUseCases,
    prompts: Prompts,
    preview_url: Callable[[int], str],
    upload_url: str,
) -> None:
    @agent.tool(
        name="list_photos",
        description=prompts.get(PromptKey.MCP_TOOL_LIST_PHOTOS),
        annotations=READ,
    )
    async def list_photos() -> PhotoList:
        library = await use_cases.list_photos(current_actor())
        return photo_list(library, PhotoLinks(preview_url, upload_url))
