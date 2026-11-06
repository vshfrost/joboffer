"""Composition root: шаблони й OAuth збираються на старті, а не під час запиту."""

from pathlib import Path

import anyio
import pytest

from application.contracts.oauth import RegisterClient
from application.ports.templates import TemplateKey, TemplatesUnavailableError
from bootstrap.container import build_container
from bootstrap.settings import Settings
from domain.oauth.errors import InvalidRedirectUri
from domain.oauth.redirect import CLAUDE_CALLBACK

CATALOG = Path(__file__).resolve().parents[2] / "templates"
TEST_DATABASE_URL = "postgresql+psycopg://app:secret-in-test@localhost:5432/app"


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBOFFER_DATABASE_URL", TEST_DATABASE_URL)


def test_container_serves_the_repository_templates_by_default() -> None:
    container = build_container(Settings(environment="test"))

    assert container.templates.get(TemplateKey.OAUTH_LOGIN) == (
        CATALOG / "oauth" / "login.html"
    ).read_text(encoding="utf-8")


def test_container_fails_at_startup_naming_the_missing_template(tmp_path: Path) -> None:
    with pytest.raises(TemplatesUnavailableError, match=r"oauth/login\.html"):
        build_container(Settings(environment="test", templates_dir=tmp_path))


def test_oauth_uses_the_redirect_allowlist_from_settings() -> None:
    container = build_container(
        Settings(
            environment="test", agent_redirect_allowlist=("https://app.example/cb",)
        )
    )
    command = RegisterClient(
        client_id="6f1c0a52-0000-4000-8000-000000000001",
        name=None,
        redirect_uris=(CLAUDE_CALLBACK,),
        metadata={},
    )

    with pytest.raises(InvalidRedirectUri):
        anyio.run(container.oauth.register_client, command)
