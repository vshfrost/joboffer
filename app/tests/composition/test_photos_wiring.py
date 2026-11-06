"""Фото підключено в composition root, HTTP-застосунок і набір тулів агента."""

import pytest

from application.photos.use_cases import PhotoUseCases
from bootstrap.api import create_app
from bootstrap.container import build_container
from bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Engine лінивий: адреса потрібна налаштуванням, сама база — ні.
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )


def test_the_container_has_photo_use_cases() -> None:
    container = build_container(Settings(environment="test"))
    assert isinstance(container.photos, PhotoUseCases)


def test_photo_routes_are_mounted() -> None:
    app = create_app(Settings(environment="test"))
    paths = app.openapi()["paths"]
    assert set(paths) >= {"/photos", "/photos/{photo_id}.jpg", "/photos/{photo_id}"}
    assert set(paths["/photos"]) == {"get", "post"}
    assert set(paths["/photos/{photo_id}"]) == {"delete"}
    assert set(paths["/photos/{photo_id}.jpg"]) == {"get"}
