"""Підготовку для вебу підключено в composition root і в HTTP-застосунок."""

import pytest

from application.prep.web import PrepWebUseCases
from bootstrap.api import create_app
from bootstrap.container import build_container
from bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Engine лінивий: адреса потрібна налаштуванням, сама база — ні.
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )


def test_the_container_has_the_prep_web_use_cases() -> None:
    container = build_container(Settings(environment="test"))
    assert isinstance(container.prep_web, PrepWebUseCases)


def test_the_prep_routes_are_mounted() -> None:
    paths = create_app(Settings(environment="test")).openapi()["paths"]
    assert set(paths["/prep/topics"]) == {"get"}
    assert set(paths["/prep/topics/{topic_id}"]) == {"get"}
    assert set(paths["/prep/steps/{step_id}/done"]) == {"post"}
    assert set(paths["/prep/topics/{topic_id}/ready"]) == {"put"}
    assert set(paths["/jobs/{job_id}/prep"]) == {"get"}
    assert set(paths["/jobs/{job_id}/interview-kit"]) == {"get"}
