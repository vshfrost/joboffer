"""Фото через HTTP наскрізь: сесія й CSRF, 422 з текстами v1, нормалізація, ізоляція користувачів,
обрив завеликого файлу під час читання."""

from collections.abc import AsyncIterator
from datetime import timedelta

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.identity import CreateUser
from bootstrap.api import container_of, create_app
from bootstrap.settings import Settings
from domain.identity.ids import UserId
from infrastructure.db.unit_of_work import unit_of_work_factory
from infrastructure.http.auth import CSRF_HEADER
from tests.integration.test_jobs_repository import NOW
from tests.integration.test_photos_repository import _cv_with_photo
from tests.integration.test_profile_http import (
    PASSWORD,
    ClientFactory,
    Session,
    make_client,
)
from tests.support.images import (
    FRAME,
    HALF_FRAME,
    decoded,
    jpeg,
    pixel,
    transparent_png,
)

__all__ = ["make_client"]

BAD_FRAME = "Фото має бути в пропорціях рамки CV (858 × 960): обери область у редакторі на сторінці профілю."
TOO_NARROW = "Обрана область вужча за 300 px — візьми більшу або фото кращої якості."
NOT_AN_IMAGE = "Фото — JPEG, PNG або WebP."
EMPTY = "Файл порожній — вибери фото."
TOO_BIG = "Фото — до 15 МБ."
MB = 1024 * 1024


class PhotosSession:
    def __init__(
        self, session: Session, portal: BlockingPortal, engine: AsyncEngine, email: str
    ) -> None:
        self.client = session.client
        self.csrf = session.csrf
        self._portal = portal
        self._engine = engine
        self._email = email

    def upload(
        self,
        data: bytes,
        label: str = "",
        *,
        name: str = "photo.jpg",
        csrf: bool = True,
    ) -> httpx2.Response:
        return self.client.post(
            "/photos",
            files={"file": (name, data, "image/jpeg")},
            data={"label": label},
            headers=self.csrf if csrf else {},
        )

    def library(self) -> httpx2.Response:
        return self.client.get("/photos")

    def jpg(self, number: object) -> httpx2.Response:
        return self.client.get(f"/photos/{number}.jpg")

    def delete(self, number: object, *, csrf: bool = True) -> httpx2.Response:
        return self.client.delete(
            f"/photos/{number}", headers=self.csrf if csrf else {}
        )

    def numbers(self) -> list[int]:
        return [p["photo_id"] for p in self.library().json()["photos"]]

    def used_in_cv(self, photo_number: int, days: int) -> None:
        """Фото пішло в CV: у Postgres `last_used_at` береться з документів."""

        async def run() -> None:
            async with self._engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": self._email},
                )
                user = UserId(row.scalar_one())
            await _cv_with_photo(
                unit_of_work_factory(self._engine),
                self._engine,
                user,
                photo_number,
                NOW + timedelta(days=days),
                days,
            )

        self._portal.call(run)


@pytest.fixture
def alice(
    make_client: ClientFactory, portal: BlockingPortal, engine: AsyncEngine
) -> PhotosSession:
    email = "alice@example.com"
    return PhotosSession(Session(make_client(), email), portal, engine, email)


@pytest.fixture
def bob(
    make_client: ClientFactory, portal: BlockingPortal, engine: AsyncEngine
) -> PhotosSession:
    email = "bob@example.com"
    return PhotosSession(Session(make_client(), email), portal, engine, email)


def problem(response: httpx2.Response, field: str, message: str) -> None:
    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "invalid_value"
    assert body["field_errors"] == [{"field": field, "message": message}]


def test_every_route_requires_a_session(make_client: ClientFactory) -> None:
    client = make_client()
    for method, path in (
        ("POST", "/photos"),
        ("GET", "/photos"),
        ("GET", "/photos/1.jpg"),
        ("DELETE", "/photos/1"),
    ):
        response = client.request(method, path)
        assert (response.status_code, response.json()["code"]) == (
            401,
            "not_authenticated",
        ), (method, path)


def test_unsafe_requests_require_the_csrf_token(alice: PhotosSession) -> None:
    assert alice.upload(jpeg(*FRAME), csrf=False).status_code == 403
    assert alice.numbers() == []

    assert alice.upload(jpeg(*FRAME)).status_code == 201
    response = alice.delete(1, csrf=False)
    assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")
    assert alice.numbers() == [1]


def test_a_new_user_has_no_photos_and_nothing_to_suggest(alice: PhotosSession) -> None:
    response = alice.library()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"photos": [], "suggested_photo_id": None}


def test_an_upload_answers_201_with_the_new_photo(alice: PhotosSession) -> None:
    response = alice.upload(jpeg(*HALF_FRAME), "Office")
    assert response.status_code == 201
    body = response.json()
    created_at = body.pop("created_at")
    assert created_at
    assert body == {
        "photo_id": 1,
        "label": "Office",
        "width": 429,
        "height": 480,
        "last_used_at": None,
    }


def test_photos_are_listed_newest_first_and_the_newest_is_suggested(
    alice: PhotosSession,
) -> None:
    alice.upload(jpeg(*FRAME), "first")
    alice.upload(jpeg(*FRAME), "second")
    body = alice.library().json()
    assert [(p["photo_id"], p["label"]) for p in body["photos"]] == [
        (2, "second"),
        (1, "first"),
    ]
    assert body["suggested_photo_id"] == 2


def test_the_last_used_photo_is_suggested_and_shows_when_it_was_used(
    alice: PhotosSession,
) -> None:
    alice.upload(jpeg(*FRAME))
    alice.upload(jpeg(*FRAME))
    alice.used_in_cv(1, days=4)
    body = alice.library().json()
    assert body["suggested_photo_id"] == 1
    used = {p["photo_id"]: p["last_used_at"] for p in body["photos"]}
    assert used[2] is None
    assert used[1] is not None


def test_a_label_is_stored_as_one_trimmed_line(alice: PhotosSession) -> None:
    alice.upload(jpeg(*FRAME), "  Office \n shot  2 ")
    assert alice.library().json()["photos"][0]["label"] == "Office shot 2"


def test_the_jpeg_is_served_to_its_owner_as_an_image(alice: PhotosSession) -> None:
    alice.upload(jpeg(*HALF_FRAME))
    response = alice.jpg(1)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    picture = decoded(response.content)
    assert (picture.format, picture.size) == ("JPEG", HALF_FRAME)


def test_a_phone_photo_is_rotated_and_loses_its_metadata(alice: PhotosSession) -> None:
    alice.upload(jpeg(480, 429, orientation=6, gps=True))
    served = alice.jpg(1).content
    picture = decoded(served)
    assert picture.size == HALF_FRAME
    assert dict(picture.getexif()) == {}
    assert b"Exif" not in served
    assert b"TestCam" not in served


def test_a_transparent_png_is_stored_on_white(alice: PhotosSession) -> None:
    response = alice.upload(transparent_png(*FRAME), name="cutout.png")
    assert response.status_code == 201
    assert min(pixel(alice.jpg(1).content, 5, 5)) >= 250


def test_a_side_over_900_px_is_scaled_down(alice: PhotosSession) -> None:
    body = alice.upload(jpeg(1716, 1920)).json()
    assert body["height"] == 900
    assert decoded(alice.jpg(1).content).size == (body["width"], 900)


def test_a_frame_in_other_proportions_is_422_and_nothing_is_saved(
    alice: PhotosSession,
) -> None:
    problem(alice.upload(jpeg(1000, 1000)), "file", BAD_FRAME)
    assert alice.numbers() == []


def test_a_frame_narrower_than_300_px_is_422_and_nothing_is_saved(
    alice: PhotosSession,
) -> None:
    problem(alice.upload(jpeg(299, 335)), "file", TOO_NARROW)
    assert alice.numbers() == []


def test_an_empty_file_is_422_and_nothing_is_saved(alice: PhotosSession) -> None:
    problem(alice.upload(b""), "file", EMPTY)
    assert alice.numbers() == []


def test_a_request_without_a_file_is_422_with_the_empty_file_text(
    alice: PhotosSession,
) -> None:
    response = alice.client.post("/photos", data={"label": "x"}, headers=alice.csrf)
    problem(response, "file", EMPTY)


def test_text_under_a_photo_name_is_422_and_nothing_is_saved(
    alice: PhotosSession,
) -> None:
    problem(
        alice.upload(b"plain text, not a picture", name="me.jpg"), "file", NOT_AN_IMAGE
    )
    assert alice.numbers() == []


def test_a_label_over_100_characters_is_422_and_nothing_is_saved(
    alice: PhotosSession,
) -> None:
    problem(
        alice.upload(jpeg(*FRAME), "я" * 101), "label", "Підпис фото — до 100 символів."
    )
    assert alice.numbers() == []


def test_a_file_over_15_mb_is_422_and_nothing_is_saved(alice: PhotosSession) -> None:
    problem(alice.upload(b"\xff\xd8" + b"0" * (15 * MB)), "file", TOO_BIG)
    assert alice.numbers() == []


def test_other_form_parts_are_ignored(alice: PhotosSession) -> None:
    response = alice.client.post(
        "/photos",
        files={
            "file": ("photo.jpg", jpeg(*FRAME), "image/jpeg"),
            "attachment": ("notes.txt", b"not a photo", "text/plain"),
        },
        data={"label": "Office", "note": "ignored"},
        headers=alice.csrf,
    )
    assert response.status_code == 201
    assert alice.library().json()["photos"][0]["label"] == "Office"


def test_a_form_that_cannot_be_parsed_is_422_like_a_missing_file(
    alice: PhotosSession,
) -> None:
    response = alice.client.post(
        "/photos",
        content=b"this is not a multipart body",
        headers={**alice.csrf, "Content-Type": "multipart/form-data; boundary=x"},
    )
    problem(response, "file", EMPTY)
    assert alice.numbers() == []


def test_another_users_photo_is_404_everywhere_and_stays_untouched(
    alice: PhotosSession, bob: PhotosSession
) -> None:
    alice.upload(jpeg(*FRAME), "mine")
    assert bob.library().json() == {"photos": [], "suggested_photo_id": None}
    for response in (bob.jpg(1), bob.delete(1)):
        assert (response.status_code, response.json()["code"]) == (404, "not_found")
    assert alice.jpg(1).status_code == 200
    assert alice.numbers() == [1]


def test_a_missing_photo_is_404_not_found(alice: PhotosSession) -> None:
    for response in (alice.jpg(7), alice.delete(7)):
        assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_deleting_removes_the_photo_for_good(alice: PhotosSession) -> None:
    alice.upload(jpeg(*FRAME))
    response = alice.delete(1)
    assert (response.status_code, response.content) == (204, b"")
    assert alice.numbers() == []
    for response in (alice.jpg(1), alice.delete(1)):
        assert (response.status_code, response.json()["code"]) == (404, "not_found")


# ---- обрив завеликого завантаження під час читання -------------------------------------------

BOUNDARY = "photo-boundary"
OPENING = (
    f"--{BOUNDARY}\r\n"
    'Content-Disposition: form-data; name="file"; filename="photo.jpg"\r\n'
    "Content-Type: image/jpeg\r\n\r\n"
).encode()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def web(
    portal: BlockingPortal, engine: AsyncEngine, database_url: str
) -> AsyncIterator[tuple[httpx2.AsyncClient, dict[str, str]]]:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
            await conn.execute(text("TRUNCATE login_failures"))

    portal.call(clean)
    app = create_app(Settings(environment="test", database_url=database_url))
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="https://testserver"
        ) as client,
    ):
        await container_of(app).identity.create_user(
            CreateUser(
                email="alice@example.com", display_name="Alice", password=PASSWORD
            )
        )
        login = await client.post(
            "/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
        )
        yield client, {CSRF_HEADER: login.json()["csrf_token"]}


class Upload:
    """Тіло завантаження, яке віддається по шматку й рахує, скільки сервер устиг прочитати."""

    def __init__(self, chunks: int) -> None:
        self.chunks = chunks
        self.read = 0

    async def body(self) -> AsyncIterator[bytes]:
        yield OPENING
        for _ in range(self.chunks):
            self.read += 1
            yield b"0" * MB


@pytest.mark.anyio
async def test_an_oversized_upload_is_cut_off_while_it_is_still_being_read(
    web: tuple[httpx2.AsyncClient, dict[str, str]],
) -> None:
    client, csrf = web
    upload = Upload(chunks=60)

    response = await client.post(
        "/photos",
        content=upload.body(),
        headers={**csrf, "Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
    )

    problem(response, "file", TOO_BIG)
    assert upload.read <= 17  # 15 МБ + рамка форми; решту 60 МБ сервер не читав


@pytest.mark.anyio
async def test_a_declared_size_over_the_limit_is_refused_before_reading_anything(
    web: tuple[httpx2.AsyncClient, dict[str, str]],
) -> None:
    client, csrf = web
    upload = Upload(chunks=5)

    response = await client.post(
        "/photos",
        content=upload.body(),
        headers={
            **csrf,
            "Content-Type": f"multipart/form-data; boundary={BOUNDARY}",
            "Content-Length": str(40 * MB),
        },
    )

    problem(response, "file", TOO_BIG)
    assert upload.read == 0
