"""Налаштування документів: тека PDF і адреса вебу для посилань; wiring у composition root."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from application.ports.documents import DocumentOutput
from bootstrap.api import create_app
from bootstrap.container import build_container
from bootstrap.settings import Settings
from infrastructure.pdf.files import FileDocuments
from infrastructure.pdf.inspector import PypdfInspector
from infrastructure.pdf.render import WeasyPrintRenderer

URL = "postgresql+psycopg://app:secret-in-test@localhost:5432/app"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DOCUMENTS_DIR", "WEB_PUBLIC_URL"):
        monkeypatch.delenv(f"JOBOFFER_{name}", raising=False)
    monkeypatch.setenv("JOBOFFER_DATABASE_URL", URL)


def test_defaults_match_the_image() -> None:
    settings = Settings()
    assert settings.documents_dir == Path("/data/documents")
    assert settings.web_public_url == "http://localhost:5174"


def test_overrides_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBOFFER_DOCUMENTS_DIR", "/srv/pdf")
    monkeypatch.setenv("JOBOFFER_WEB_PUBLIC_URL", "https://web.example")

    settings = Settings()

    assert (settings.documents_dir, settings.web_public_url) == (
        Path("/srv/pdf"),
        "https://web.example",
    )


def test_the_container_writes_pdfs_to_the_configured_folder(tmp_path: Path) -> None:
    container = build_container(
        Settings(environment="test", documents_dir=tmp_path / "pdf")
    )

    output = container.documents._output
    assert isinstance(output, DocumentOutput)
    assert isinstance(output.renderer, WeasyPrintRenderer)
    assert isinstance(output.inspector, PypdfInspector)
    assert isinstance(output.files, FileDocuments)
    assert output.files._root == tmp_path / "pdf"


def test_the_pdf_route_is_mounted() -> None:
    app = create_app(Settings(environment="test"))
    paths = app.openapi()["paths"]
    assert set(paths["/documents/{document_id}/pdf"]) == {"get"}


def test_the_pdf_route_requires_a_session() -> None:
    with TestClient(create_app(Settings(environment="test"))) as client:
        response = client.get("/documents/1/pdf")
    assert response.status_code == 401


def test_the_job_documents_route_is_mounted() -> None:
    app = create_app(Settings(environment="test"))
    paths = app.openapi()["paths"]
    assert set(paths["/jobs/{job_id}/documents"]) == {"get"}
