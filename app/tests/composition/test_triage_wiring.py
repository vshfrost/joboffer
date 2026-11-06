"""Тріаж підключено в composition root і в MCP-агент."""

import pytest

from application.triage.use_cases import TriageUseCases
from bootstrap.container import build_container
from bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Engine лінивий: адреса потрібна налаштуванням, сама база — ні.
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )


def test_the_container_has_triage_use_cases() -> None:
    container = build_container(Settings(environment="test"))
    assert isinstance(container.triage, TriageUseCases)
