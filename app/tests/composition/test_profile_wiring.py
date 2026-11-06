"""Профіль підключено в composition root і в HTTP-застосунок."""

import pytest

from application.profile.use_cases import ProfileUseCases
from bootstrap.api import create_app
from bootstrap.container import build_container
from bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Engine лінивий: адреса потрібна налаштуванням, сама база — ні.
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )


def test_the_container_has_profile_use_cases() -> None:
    container = build_container(Settings(environment="test"))
    assert isinstance(container.profile, ProfileUseCases)


def test_profile_routes_are_mounted() -> None:
    app = create_app(Settings(environment="test"))
    paths = set(app.openapi()["paths"])
    assert {"/profile", "/profile/target", "/profile/locations"} <= paths
    assert {"/profile/rules", "/profile/contacts"} <= paths
