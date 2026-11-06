"""Документи підключено в composition root."""

import pytest

from application.documents.use_cases import DocumentUseCases
from bootstrap.container import build_container
from bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Engine лінивий: адреса потрібна налаштуванням, сама база — ні.
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )


def test_the_container_has_document_use_cases() -> None:
    container = build_container(Settings(environment="test"))
    assert isinstance(container.documents, DocumentUseCases)
