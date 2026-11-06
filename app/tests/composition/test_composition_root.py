"""Composition root — незалежні екземпляри, settings лише з bootstrap."""

from typing import Any

import pytest
from pydantic import ValidationError

from bootstrap.api import container_of, create_app
from bootstrap.container import build_container
from bootstrap.settings import Settings

PREFIX = "JOBOFFER_"

TEST_DATABASE_URL = "postgresql+psycopg://app:secret-in-test@localhost:5432/app"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        f"{PREFIX}ENVIRONMENT",
        f"{PREFIX}API_HOST",
        f"{PREFIX}API_PORT",
    ):
        monkeypatch.delenv(name, raising=False)
    # Engine лінивий: адреса потрібна налаштуванням, сама база в composition-тестах — ні.
    monkeypatch.setenv(f"{PREFIX}DATABASE_URL", TEST_DATABASE_URL)


def test_two_apps_are_independent() -> None:
    first = create_app(Settings(environment="test", api_port=8801))
    second = create_app(Settings(environment="test", api_port=8802))

    assert first is not second
    assert container_of(first) is not container_of(second)
    assert container_of(first).settings.api_port == 8801
    assert container_of(second).settings.api_port == 8802


def test_each_container_is_built_fresh() -> None:
    settings = Settings(environment="test")
    assert build_container(settings) is not build_container(settings)


def test_settings_come_from_environment_with_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(f"{PREFIX}API_PORT", "9001")
    monkeypatch.setenv(f"{PREFIX}ENVIRONMENT", "staging")
    settings = container_of(create_app()).settings
    assert (settings.api_port, settings.environment) == (9001, "staging")


def test_env_is_read_per_app_not_once_globally(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}API_PORT", "9001")
    before = create_app()
    monkeypatch.setenv(f"{PREFIX}API_PORT", "9002")
    after = create_app()
    assert container_of(before).settings.api_port == 9001
    assert container_of(after).settings.api_port == 9002


def test_settings_are_immutable() -> None:
    settings = Settings()
    with pytest.raises(ValidationError):
        settings.api_port = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("api_port", "0"),
        ("api_port", "70000"),
        ("environment", "qa"),
    ],
)
def test_invalid_settings_rejected(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    monkeypatch.setenv(f"{PREFIX}{field.upper()}", value)
    with pytest.raises(ValidationError):
        Settings()


def test_app_is_not_mounted_under_a_path_prefix() -> None:
    assert create_app(Settings(environment="test")).root_path == ""


def test_base_path_setting_is_gone() -> None:
    assert "base_path" not in Settings.model_fields
    separate: dict[str, Any] = {"base_path": "/sample"}
    with pytest.raises(ValidationError):
        Settings(**separate)


def test_container_of_rejects_foreign_state() -> None:
    app = create_app(Settings(environment="test"))
    app.state.container = object()
    with pytest.raises(TypeError, match="Container"):
        container_of(app)


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(f"{PREFIX}DATABASE_URL")
    with pytest.raises(ValidationError, match="database_url"):
        Settings()


def test_database_password_is_not_in_repr() -> None:
    settings = Settings()
    assert settings.database_url.get_secret_value() == TEST_DATABASE_URL
    assert "secret-in-test" not in repr(settings)


def test_container_wires_engine_and_unit_of_work() -> None:
    container = container_of(create_app())
    assert container.engine.dialect.driver == "psycopg"
    assert container.unit_of_work() is not container.unit_of_work()
