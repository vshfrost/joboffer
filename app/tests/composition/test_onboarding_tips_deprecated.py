"""Підказки «Перших кроків» застаріли: маршрути лишаються робочими, але позначені deprecated в OpenAPI."""

import pytest

from bootstrap.api import create_app
from bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Engine лінивий: адреса потрібна налаштуванням, сама база — ні.
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )


def test_tip_routes_are_marked_deprecated() -> None:
    paths = create_app(Settings(environment="test")).openapi()["paths"]

    assert paths["/onboarding/tips/{key}/seen"]["post"]["deprecated"] is True
    assert paths["/onboarding/tips/{key}/dismiss"]["post"]["deprecated"] is True


def test_the_onboarding_read_route_is_not_deprecated() -> None:
    paths = create_app(Settings(environment="test")).openapi()["paths"]

    assert paths["/onboarding"]["get"].get("deprecated") is not True
