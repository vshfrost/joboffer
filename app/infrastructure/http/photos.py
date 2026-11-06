"""HTTP фото для шапки CV: завантаження кадру, список, JPEG, видалення.

`photo_id` у URL і відповідях — номер фото в межах користувача (ціле, з 1); внутрішній UUID
назовні не виходить. Тіло завантаження читається з лімітом: завелике обривається ще під час
читання, а не після того, як усе лежить у памʼяті.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from python_multipart.multipart import Field, File, create_form_parser

from application.contracts.actor import Actor
from application.contracts.photos import PhotoData
from application.photos.use_cases import PhotoUseCases
from domain.photos.errors import photo_too_large
from domain.photos.photo import MAX_UPLOAD_BYTES
from infrastructure.http.auth import HttpAuth

# Файл плюс рамки multipart-форми (межі частин, заголовки, поле `label`).
FORM_OVERHEAD = 64 * 1024
MAX_BODY_BYTES = MAX_UPLOAD_BYTES + FORM_OVERHEAD


class PhotoModel(BaseModel):
    photo_id: int
    label: str
    width: int
    height: int
    created_at: datetime
    last_used_at: datetime | None


class PhotoLibraryModel(BaseModel):
    photos: list[PhotoModel]
    suggested_photo_id: int | None


def _photo(photo: PhotoData) -> PhotoModel:
    return PhotoModel(
        photo_id=photo.photo_number,
        label=photo.label,
        width=photo.width,
        height=photo.height,
        created_at=photo.created_at,
        last_used_at=photo.last_used_at,
    )


async def _bounded_body(request: Request) -> AsyncIterator[bytes]:
    """Тіло запиту по шматках; перевищення ліміту рветься з помилкою `file` одразу, не дочитуючи."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise photo_too_large()
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > MAX_BODY_BYTES:
            raise photo_too_large()
        yield chunk


async def _read_upload(request: Request) -> tuple[bytes | None, str]:
    """Поля `file` і `label` з multipart-форми. Файл тримається в памʼяті (ліміт — `MAX_BODY_BYTES`),
    тимчасових файлів на диску нема. Зламана форма — як відсутній файл."""
    content: bytes | None = None
    label = ""

    def on_field(field: Field) -> None:
        nonlocal label
        if field.field_name == b"label":
            label = (field.value or b"").decode("utf-8", errors="replace")

    def on_file(file: File) -> None:
        nonlocal content
        if file.field_name == b"file":
            file.file_object.seek(0)
            content = file.file_object.read()

    try:
        parser = create_form_parser(
            request.headers,  # type: ignore[arg-type]
            on_field,
            on_file,
            {"MAX_MEMORY_FILE_SIZE": MAX_BODY_BYTES + 1},
        )
        async for chunk in _bounded_body(request):
            parser.write(chunk)
        parser.finalize()
    except ValueError:
        return None, ""
    return content, label


def photos_router(photos: PhotoUseCases, auth: HttpAuth) -> APIRouter:
    router = APIRouter(prefix="/photos", tags=["photos"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    def private(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    @router.post("", status_code=201)
    async def upload(request: Request, actor: Caller, response: Response) -> PhotoModel:
        private(response)
        data, label = await _read_upload(request)
        return _photo(await photos.add_photo(actor, data or b"", label))

    @router.get("")
    async def library(actor: Caller, response: Response) -> PhotoLibraryModel:
        private(response)
        found = await photos.list_photos(actor)
        return PhotoLibraryModel(
            photos=[_photo(photo) for photo in found.photos],
            suggested_photo_id=found.suggested_photo_number,
        )

    @router.get("/{photo_id}.jpg", response_class=Response)
    async def jpeg(photo_id: int, actor: Caller) -> Response:
        data = await photos.read_photo(actor, photo_id)
        return Response(
            data, media_type="image/jpeg", headers={"Cache-Control": "no-store"}
        )

    @router.delete("/{photo_id}", status_code=204)
    async def delete(photo_id: int, actor: Caller) -> Response:
        await photos.delete_photo(actor, photo_id)
        return Response(status_code=204)

    return router
