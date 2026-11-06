"""Налаштування входу через Google: усе або нічого; без них Google вимкнено."""

from typing import Any

import pytest
from pydantic import ValidationError

from bootstrap.container import build_container
from bootstrap.settings import Settings

PREFIX = "JOBOFFER_"
URL = "postgresql+psycopg://app:secret-in-test@localhost:5432/app"
FULL: dict[str, Any] = {
    "google_client_id": "client-id.apps.googleusercontent.com",
    "google_client_secret": "test-google-secret",
    "google_redirect_uri": "https://app.example/api/auth/google/callback",
    "auth_state_secret": "test-state-secret-0123456789abcdef",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REDIRECT_URI",
        "GOOGLE_GATE_REDIRECT_URI",
        "GOOGLE_METADATA_URL",
        "AUTH_STATE_SECRET",
    ):
        monkeypatch.delenv(f"{PREFIX}{name}", raising=False)
    monkeypatch.setenv(f"{PREFIX}DATABASE_URL", URL)


def test_google_is_off_by_default() -> None:
    settings = Settings()

    assert settings.google_enabled is False
    assert (
        settings.google_metadata_url
        == "https://accounts.google.com/.well-known/openid-configuration"
    )
    assert build_container(settings).google is None


def test_full_configuration_turns_google_on() -> None:
    settings = Settings(**FULL)

    assert settings.google_enabled is True
    assert build_container(settings).google is not None


def test_values_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in FULL.items():
        monkeypatch.setenv(f"{PREFIX}{name.upper()}", value)

    assert Settings().google_enabled is True


@pytest.mark.parametrize("missing", sorted(FULL))
def test_partial_configuration_is_refused(missing: str) -> None:
    partial = {name: value for name, value in FULL.items() if name != missing}

    with pytest.raises(ValidationError):
        Settings(**partial)


@pytest.mark.parametrize(
    "redirect",
    [
        "app.example/callback",
        "ftp://app.example/callback",
        "https://app.example/cb#frag",
        "",
    ],
)
def test_redirect_uri_must_be_an_http_address_without_a_fragment(redirect: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{**FULL, "google_redirect_uri": redirect})


def test_secrets_are_hidden_in_repr() -> None:
    text = repr(Settings(**FULL))

    assert FULL["google_client_secret"] not in text
    assert FULL["auth_state_secret"] not in text


def test_state_secret_must_be_long_enough() -> None:
    with pytest.raises(ValidationError):
        Settings(**{**FULL, "auth_state_secret": "short"})


GATE = "http://localhost:5174/mcp/auth/google/callback"


def test_gate_is_off_without_its_redirect_uri() -> None:
    container = build_container(Settings(**FULL))

    assert container.google is not None
    assert container.google_gate is None
    assert Settings(**FULL).google_gate_enabled is False


def test_gate_is_on_with_its_own_redirect_uri() -> None:
    settings = Settings(**FULL, google_gate_redirect_uri=GATE)
    container = build_container(settings)

    assert settings.google_gate_enabled is True
    assert container.google_gate is not None
    assert container.google_gate.config.redirect_uri == GATE
    assert container.google is not None
    assert container.google.config.redirect_uri == FULL["google_redirect_uri"]


def test_gate_redirect_uri_without_google_is_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(google_gate_redirect_uri=GATE)


@pytest.mark.parametrize(
    "uri", ["agent.example/cb", "ftp://agent.example/cb", "https://agent.example/cb#x"]
)
def test_gate_redirect_uri_must_be_an_http_address_without_a_fragment(uri: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**FULL, google_gate_redirect_uri=uri)


@pytest.mark.parametrize(
    "uri",
    [
        "http://127.0.0.1:8798/mcp/auth/google/callback",  # інший origin, ніж у вебу
        "http://localhost:5174/mcp/auth/google/start",  # не callback
        "http://localhost:5174/mcp/login/google/callback",  # старий шлях гейта
    ],
)
def test_gate_redirect_uri_must_be_the_mcp_callback_of_the_web_origin(uri: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**FULL, google_gate_redirect_uri=uri)


def test_gate_redirect_uri_follows_the_web_origin() -> None:
    settings = Settings(
        **FULL,
        web_public_url="https://jobs.example.com",
        google_gate_redirect_uri="https://jobs.example.com/mcp/auth/google/callback",
    )

    assert settings.google_gate_enabled is True


def test_blank_gate_redirect_uri_means_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}GOOGLE_GATE_REDIRECT_URI", "")

    assert Settings().google_gate_redirect_uri is None
