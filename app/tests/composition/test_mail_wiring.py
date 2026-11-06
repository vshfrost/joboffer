"""Пошта користувача підключена в composition root, HTTP-застосунок і набір MCP-тулів."""

import pytest

from application.mail.inbox import MailUseCases
from bootstrap.api import create_app
from bootstrap.container import build_container
from bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Engine лінивий: адреса потрібна налаштуванням, сама база — ні.
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
    )
    monkeypatch.delenv("JOBOFFER_MAIL_ADDRESS", raising=False)


def test_the_container_has_mail_use_cases() -> None:
    container = build_container(Settings(environment="test"))

    assert isinstance(container.mail, MailUseCases)


def test_mail_routes_are_mounted() -> None:
    paths = create_app(Settings(environment="test")).openapi()["paths"]

    assert set(paths["/mail"]) == {"get"}
    assert set(paths["/mail/settings"]) == {"get"}
    assert set(paths["/mail/sync"]) == {"post"}
    assert set(paths["/mail/address/rotate"]) == {"post"}
    assert set(paths["/mail/{mail_id}"]) == {"get"}


def test_the_mailbox_address_comes_from_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOBOFFER_MAIL_ADDRESS", "mailroom@example.com")

    settings = Settings(environment="test")

    assert settings.mail_address == "mailroom@example.com"
