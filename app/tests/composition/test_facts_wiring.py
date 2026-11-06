"""Факти підключено в composition root і в HTTP-застосунок."""

import pytest

from application.facts.use_cases import FactUseCases
from bootstrap.api import create_app
from bootstrap.container import build_container
from bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Engine лінивий: адреса потрібна налаштуванням, сама база — ні.
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )


def test_the_container_has_fact_use_cases() -> None:
    container = build_container(Settings(environment="test"))
    assert isinstance(container.facts, FactUseCases)


def test_fact_routes_are_mounted() -> None:
    app = create_app(Settings(environment="test"))
    paths = app.openapi()["paths"]
    assert set(paths) >= {
        "/facts",
        "/facts/original-cv",
        "/facts/confirm",
        "/facts/{fact_id}",
    }
    assert set(paths["/facts/{fact_id}"]) == {"put", "delete"}
