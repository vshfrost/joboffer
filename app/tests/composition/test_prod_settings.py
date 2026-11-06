"""Prod-гард Settings: з JOBOFFER_ENVIRONMENT=prod застосунок не стартує на послаблених значеннях."""

import pytest
from pydantic import ValidationError

from bootstrap.settings import Settings

PREFIX = "JOBOFFER_"
URL = "postgresql+psycopg://app:secret-in-test@localhost:5432/app"
STATE_SECRET = "s" * 32
WEB = "https://jobs.example.com"
GOOGLE = {
    "GOOGLE_CLIENT_ID": "client-id",
    "GOOGLE_CLIENT_SECRET": "client-secret",
    "GOOGLE_REDIRECT_URI": f"{WEB}/api/auth/google/callback",
    "AUTH_STATE_SECRET": STATE_SECRET,
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}DATABASE_URL", URL)
    monkeypatch.setenv(f"{PREFIX}ENVIRONMENT", "prod")


def prod(monkeypatch: pytest.MonkeyPatch, **values: str) -> Settings:
    for name, value in values.items():
        monkeypatch.setenv(f"{PREFIX}{name}", value)
    return Settings()


def test_job_containers_with_only_the_database_url_start_in_prod() -> None:
    assert Settings().environment == "prod"


def test_a_complete_prod_setup_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = prod(
        monkeypatch,
        COOKIE_SECURE="true",
        TRUSTED_PROXIES="1",
        CLIENT_IP_HEADER="cf-connecting-ip",
        WEB_PUBLIC_URL=WEB,
        AGENT_ALLOWED_HOSTS='["jobs.example.com"]',
        **GOOGLE,
    )

    assert settings.cookie_secure


def test_insecure_cookie_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        prod(monkeypatch, COOKIE_SECURE="false")


def test_plain_http_web_url_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="web_public_url"):
        prod(monkeypatch, WEB_PUBLIC_URL="http://jobs.example.com")


def test_plain_http_google_redirect_fails_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValidationError, match="google_redirect_uri"):
        prod(
            monkeypatch,
            WEB_PUBLIC_URL=WEB,
            **{
                **GOOGLE,
                "GOOGLE_REDIRECT_URI": "http://jobs.example.com/api/auth/google/callback",
            },
        )


def test_wildcard_agent_host_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="agent_allowed_hosts"):
        prod(monkeypatch, AGENT_ALLOWED_HOSTS='["*"]')


def test_plain_http_redirect_in_the_agent_allowlist_fails_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValidationError, match="agent_redirect_allowlist"):
        prod(
            monkeypatch,
            AGENT_REDIRECT_ALLOWLIST='["http://claude.ai/api/mcp/auth_callback"]',
        )


@pytest.mark.parametrize("environment", ["dev", "test", "staging"])
def test_the_same_insecure_values_are_allowed_outside_prod(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    settings = prod(
        monkeypatch,
        ENVIRONMENT=environment,
        COOKIE_SECURE="false",
        WEB_PUBLIC_URL="http://jobs.example.com",
        AGENT_ALLOWED_HOSTS='["*"]',
    )

    assert not settings.cookie_secure
