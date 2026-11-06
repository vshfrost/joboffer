"""Налаштування агента: типові значення, перевизначення з оточення, публічна адреса = <origin вебу>/mcp."""

from typing import Any

import pytest
from pydantic import ValidationError

from bootstrap.settings import Settings

PREFIX = "JOBOFFER_"
URL = "postgresql+psycopg://app:secret-in-test@localhost:5432/app"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "WEB_PUBLIC_URL",
        "AGENT_ALLOWED_HOSTS",
        "AGENT_REDIRECT_ALLOWLIST",
    ):
        monkeypatch.delenv(f"{PREFIX}{name}", raising=False)
    monkeypatch.setenv(f"{PREFIX}DATABASE_URL", URL)


def test_defaults() -> None:
    settings = Settings()

    assert settings.agent_public_url == "http://localhost:5174/mcp"
    assert settings.agent_allowed_hosts == ("127.0.0.1:*", "localhost:*")
    assert settings.agent_redirect_allowlist == (
        "https://claude.ai/api/mcp/auth_callback",
        "loopback",
    )


def test_overrides_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}AGENT_ALLOWED_HOSTS", '["agent.example"]')
    monkeypatch.setenv(
        f"{PREFIX}AGENT_REDIRECT_ALLOWLIST", '["https://app.example/cb/*"]'
    )

    settings = Settings()

    assert settings.agent_allowed_hosts == ("agent.example",)
    assert settings.agent_redirect_allowlist == ("https://app.example/cb/*",)


def test_agent_address_is_derived_from_the_web_public_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(f"{PREFIX}WEB_PUBLIC_URL", "https://jobs.example.com")

    assert Settings().agent_public_url == "https://jobs.example.com/mcp"


@pytest.mark.parametrize(
    "web_url",
    ["https://jobs.example.com/", "https://jobs.example.com/sample/"],
)
def test_agent_address_is_the_origin_of_the_web_url_whatever_its_path(
    web_url: str,
) -> None:
    assert Settings(web_public_url=web_url).agent_public_url == (
        "https://jobs.example.com/mcp"
    )


def test_agent_address_of_the_default_web_url() -> None:
    assert Settings().agent_public_url == "http://localhost:5174/mcp"


def test_agent_address_cannot_be_set_separately() -> None:
    separate: dict[str, Any] = {"agent_public_url": "https://agent.example/sample"}

    with pytest.raises(ValidationError):
        Settings(**separate)


@pytest.mark.parametrize(
    "web_url",
    ["jobs.example.com", "ftp://jobs.example.com", "https://", ""],
)
def test_web_public_url_must_be_an_http_address(web_url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(web_public_url=web_url)
