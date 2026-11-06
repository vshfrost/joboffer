"""Відправка листів у composition root: окремий токен gmail.send, ліміт з оточення, реєстрація
закрита без токена, процеси синку й відправки не бачать токенів одне одного."""

import re
from pathlib import Path

import pytest

from application.mail.outgoing import OutgoingMailUseCases
from bootstrap.container import build_container
from bootstrap.settings import Settings

COMPOSE = Path(__file__).parents[3] / "infra" / "compose.yaml"
SEND_ENV = (
    "JOBOFFER_MAIL_ADDRESS",
    "JOBOFFER_GMAIL_CLIENT_ID",
    "JOBOFFER_GMAIL_CLIENT_SECRET",
    "JOBOFFER_GMAIL_SEND_REFRESH_TOKEN",
)
SEND_TOKEN = "JOBOFFER_GMAIL_SEND_REFRESH_TOKEN"
SYNC_TOKEN = "JOBOFFER_GMAIL_REFRESH_TOKEN"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )
    for name in (*SEND_ENV, "JOBOFFER_MAIL_SEND_DAILY_LIMIT", SYNC_TOKEN):
        monkeypatch.delenv(name, raising=False)


def set_send_env(monkeypatch: pytest.MonkeyPatch, *, skip: str = "") -> None:
    for name in SEND_ENV:
        if name != skip:
            monkeypatch.setenv(
                name, "x@example.com" if name.endswith("ADDRESS") else "x"
            )


def test_without_the_send_token_registration_is_closed_and_nothing_can_send() -> None:
    container = build_container(Settings(environment="test"))

    assert container.registration_open is False
    assert container.outgoing_mail is None


def test_with_the_send_token_registration_is_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_send_env(monkeypatch)

    container = build_container(Settings(environment="test"))

    assert container.registration_open is True
    assert isinstance(container.outgoing_mail, OutgoingMailUseCases)


@pytest.mark.parametrize("missing", SEND_ENV)
def test_registration_stays_closed_while_any_sending_setting_is_missing(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    set_send_env(monkeypatch, skip=missing)

    container = build_container(Settings(environment="test"))

    assert container.registration_open is False
    assert container.outgoing_mail is None


def test_the_daily_limit_defaults_to_50_and_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings(environment="test").mail_send_daily_limit == 50

    monkeypatch.setenv("JOBOFFER_MAIL_SEND_DAILY_LIMIT", "7")

    assert Settings(environment="test").mail_send_daily_limit == 7


def test_blank_send_token_from_compose_means_unset_and_a_real_one_stays_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SEND_TOKEN, "")
    assert Settings(environment="test").gmail_send_refresh_token is None

    monkeypatch.setenv(SEND_TOKEN, "send-secret-x")
    settings = Settings(environment="test")

    assert settings.gmail_send_refresh_token is not None
    assert settings.gmail_send_refresh_token.get_secret_value() == "send-secret-x"
    assert "send-secret-x" not in repr(settings)


def compose_services() -> dict[str, str]:
    """Текст кожного сервісу compose-файлу (ключі другого рівня під `services:`)."""
    text = COMPOSE.read_text()
    block = text.split("\nservices:\n", 1)[1]
    parts = re.split(r"^  ([a-z-]+):\n", block, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_only_the_app_service_gets_the_send_token() -> None:
    services = compose_services()

    holders = {name for name, body in services.items() if SEND_TOKEN in body}

    assert holders == {"app"}


def test_the_sync_service_has_no_send_token_and_nobody_else_has_the_sync_token() -> (
    None
):
    services = compose_services()

    assert SEND_TOKEN not in services["mailsync"]
    assert {name for name, body in services.items() if SYNC_TOKEN in body} == {
        "mailsync"
    }
