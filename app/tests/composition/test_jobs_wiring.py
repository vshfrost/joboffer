"""Вакансії підключено в composition root і в HTTP-застосунок."""

import pytest

from application.jobs.use_cases import JobUseCases
from bootstrap.api import create_app
from bootstrap.container import build_container
from bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Engine лінивий: адреса потрібна налаштуванням, сама база — ні.
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )


def test_the_container_has_job_use_cases() -> None:
    container = build_container(Settings(environment="test"))
    assert isinstance(container.jobs, JobUseCases)


def test_job_routes_are_mounted() -> None:
    app = create_app(Settings(environment="test"))
    paths = set(app.openapi()["paths"])
    assert {"/jobs", "/jobs/{job_id}", "/jobs/dismiss"} <= paths
    assert "/jobs/{job_id}/restore" in paths
