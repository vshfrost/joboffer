"""E2E: застосунок наскрізь через його транспорти. Не входять у core-only."""

import pytest


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Адреса для Settings; ці тести БД не торкаються (engine лінивий). З БД — tests/integration."""
    name = "JOBOFFER_DATABASE_URL"
    monkeypatch.setenv(name, "postgresql+psycopg://app:app@localhost:5432/app")
