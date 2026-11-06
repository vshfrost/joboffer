"""Подачі підключено в composition root, HTTP-застосунок і набір MCP-тулів."""

import pytest

from application.applications.use_cases import ApplicationUseCases
from bootstrap.api import create_app
from bootstrap.container import build_container
from bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Engine лінивий: адреса потрібна налаштуванням, сама база — ні.
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )


def test_the_container_has_application_use_cases() -> None:
    container = build_container(Settings(environment="test"))
    assert isinstance(container.applications, ApplicationUseCases)


def test_application_routes_are_mounted() -> None:
    app = create_app(Settings(environment="test"))
    paths = app.openapi()["paths"]
    assert set(paths["/jobs/{job_id}/application"]) == {"get", "put"}
    assert set(paths["/jobs/{job_id}/application/status"]) == {"post"}
