"""Налаштування сесій: типові значення, перевизначення з оточення, межі."""

import pytest
from pydantic import ValidationError

from bootstrap.settings import Settings

PREFIX = "JOBOFFER_"
URL = "postgresql+psycopg://app:secret-in-test@localhost:5432/app"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SESSION_IDLE_HOURS",
        "SESSION_ABSOLUTE_DAYS",
        "SESSION_COOKIE_NAME",
        "COOKIE_SECURE",
        "TRUSTED_PROXIES",
        "CLIENT_IP_HEADER",
    ):
        monkeypatch.delenv(f"{PREFIX}{name}", raising=False)
    monkeypatch.setenv(f"{PREFIX}DATABASE_URL", URL)


def test_defaults() -> None:
    settings = Settings()
    assert (
        settings.session_idle_hours,
        settings.session_absolute_days,
        settings.session_cookie,
        settings.cookie_secure,
        settings.trusted_proxies,
        settings.client_ip_header,
    ) == (12, 30, "__Host-joboffer_session", True, 0, None)


def test_insecure_dev_cookie_drops_the_host_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Браузер відкидає __Host- без Secure, тож dev по http лишає просте ім'я.
    monkeypatch.setenv(f"{PREFIX}COOKIE_SECURE", "false")
    assert Settings().session_cookie == "joboffer_session"


def test_explicit_cookie_name_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}SESSION_COOKIE_NAME", "custom_session")
    assert Settings().session_cookie == "custom_session"


def test_host_prefixed_name_requires_secure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}SESSION_COOKIE_NAME", "__Host-joboffer_session")
    monkeypatch.setenv(f"{PREFIX}COOKIE_SECURE", "false")
    with pytest.raises(ValidationError, match="__Host-"):
        Settings()


def test_client_ip_header_is_lowercased(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}CLIENT_IP_HEADER", "CF-Connecting-IP")
    assert Settings().client_ip_header == "cf-connecting-ip"


def test_blank_client_ip_header_means_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}CLIENT_IP_HEADER", "")
    assert Settings().client_ip_header is None


def test_overrides_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}SESSION_IDLE_HOURS", "2")
    monkeypatch.setenv(f"{PREFIX}SESSION_ABSOLUTE_DAYS", "7")
    monkeypatch.setenv(f"{PREFIX}COOKIE_SECURE", "false")
    monkeypatch.setenv(f"{PREFIX}TRUSTED_PROXIES", "1")
    settings = Settings()
    assert (
        settings.session_idle_hours,
        settings.session_absolute_days,
        settings.cookie_secure,
        settings.trusted_proxies,
    ) == (2, 7, False, 1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("SESSION_IDLE_HOURS", "0"),
        ("SESSION_ABSOLUTE_DAYS", "0"),
        ("SESSION_ABSOLUTE_DAYS", "366"),
        ("SESSION_COOKIE_NAME", "has space"),
        ("TRUSTED_PROXIES", "-1"),
        ("TRUSTED_PROXIES", "6"),
        ("CLIENT_IP_HEADER", "has space"),
    ],
)
def test_invalid_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    monkeypatch.setenv(f"{PREFIX}{field}", value)
    with pytest.raises(ValidationError):
        Settings()


def test_idle_cannot_outlive_the_absolute_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(f"{PREFIX}SESSION_IDLE_HOURS", "25")
    monkeypatch.setenv(f"{PREFIX}SESSION_ABSOLUTE_DAYS", "1")
    with pytest.raises(ValidationError, match="session_idle_hours"):
        Settings()
