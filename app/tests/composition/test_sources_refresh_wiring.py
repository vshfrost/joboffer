"""«Оновити зараз» і «уже не проходять фільтр» підключені в composition root і в HTTP-застосунок."""

import pytest

from application.sources.filtered import FilteredJobUseCases
from application.sources.overview import SourceOverviewUseCases
from bootstrap.api import create_app
from bootstrap.container import build_container
from bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Engine лінивий: адреса потрібна налаштуванням, сама база — ні.
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )


def test_the_container_has_the_overview_and_filtered_use_cases() -> None:
    container = build_container(Settings(environment="test"))

    assert isinstance(container.source_overview, SourceOverviewUseCases)
    assert isinstance(container.source_filtered, FilteredJobUseCases)


def test_refresh_and_filtered_routes_are_mounted() -> None:
    paths = create_app(Settings(environment="test")).openapi()["paths"]

    assert set(paths["/sources"]) == {"get"}
    assert set(paths.get("/sources/refresh", {})) == {"post"}
    assert set(paths.get("/sources/filtered", {})) == {"get"}
    assert set(paths.get("/sources/filtered/dismiss", {})) == {"post"}
