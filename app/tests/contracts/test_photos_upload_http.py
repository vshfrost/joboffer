"""Завантаження фото: завелике тіло відсікається під час читання, а не після того, як усе лежить у памʼяті."""

from collections.abc import AsyncIterator
from typing import cast
from uuid import UUID

import httpx2
import pytest
from fastapi import FastAPI, Request

from application.contracts.actor import Actor, Channel, Scope
from application.photos.use_cases import PhotoUseCases
from domain.identity.ids import UserId
from infrastructure.http.auth import HttpAuth
from infrastructure.http.errors import install_error_handlers
from infrastructure.http.photos import photos_router

pytestmark = pytest.mark.anyio

MB = 1024 * 1024
BOUNDARY = "photo-boundary"
OPENING = (
    f"--{BOUNDARY}\r\n"
    'Content-Disposition: form-data; name="file"; filename="photo.jpg"\r\n'
    "Content-Type: image/jpeg\r\n\r\n"
).encode()
HEADERS = {"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class SignedIn:
    async def actor(self, request: Request) -> Actor:
        return Actor(
            user_id=UserId(UUID(int=1)),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )


class NeverCalled:
    async def add_photo(self, actor: Actor, data: bytes, label: str = "") -> object:
        raise AssertionError("завелике фото дійшло до use case")


@pytest.fixture
def client() -> httpx2.AsyncClient:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(
        photos_router(cast(PhotoUseCases, NeverCalled()), cast(HttpAuth, SignedIn()))
    )
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    )


class Upload:
    """Тіло, яке віддається по мегабайту й рахує, скільки сервер устиг прочитати."""

    def __init__(self, chunks: int) -> None:
        self.chunks = chunks
        self.read = 0

    async def body(self) -> AsyncIterator[bytes]:
        yield OPENING
        for _ in range(self.chunks):
            self.read += 1
            yield b"0" * MB


async def test_a_6_mb_upload_is_refused_after_at_most_7_mb_were_read(
    client: httpx2.AsyncClient,
) -> None:
    upload = Upload(chunks=60)

    response = await client.post("/photos", content=upload.body(), headers=HEADERS)

    assert upload.read <= 7
    assert response.status_code == 422
    assert response.json()["field_errors"] == [
        {"field": "file", "message": "Фото — до 5 МБ."}
    ]


async def test_a_declared_length_over_the_limit_is_refused_before_reading_anything(
    client: httpx2.AsyncClient,
) -> None:
    upload = Upload(chunks=5)

    response = await client.post(
        "/photos",
        content=upload.body(),
        headers={**HEADERS, "Content-Length": str(40 * MB)},
    )

    assert response.status_code == 422
    assert upload.read == 0
