"""Налаштування altcha: ключ (≥ 32 символи, порожній = не задано) і JOBOFFER_ALTCHA_MAXNUMBER."""

import pytest
from pydantic import ValidationError

from bootstrap.settings import Settings
from tests.support.altcha import TEST_KEY

PREFIX = "JOBOFFER_"
URL = "postgresql+psycopg://app:secret-in-test@localhost:5432/app"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ALTCHA_HMAC_KEY", "ALTCHA_MAXNUMBER"):
        monkeypatch.delenv(f"{PREFIX}{name}", raising=False)
    monkeypatch.setenv(f"{PREFIX}DATABASE_URL", URL)


def test_defaults_leave_registration_closed() -> None:
    settings = Settings()
    assert (settings.altcha_hmac_key, settings.altcha_maxnumber) == (None, 100_000)


def test_key_and_maxnumber_come_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(f"{PREFIX}ALTCHA_HMAC_KEY", TEST_KEY)
    monkeypatch.setenv(f"{PREFIX}ALTCHA_MAXNUMBER", "2500")
    settings = Settings()
    assert settings.altcha_hmac_key is not None
    assert settings.altcha_hmac_key.get_secret_value() == TEST_KEY
    assert settings.altcha_maxnumber == 2500


def test_blank_key_means_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    # Compose передає порожній рядок, коли змінної в infra/.env нема.
    monkeypatch.setenv(f"{PREFIX}ALTCHA_HMAC_KEY", "")
    assert Settings().altcha_hmac_key is None


def test_key_shorter_than_32_characters_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(f"{PREFIX}ALTCHA_HMAC_KEY", "x" * 31)
    with pytest.raises(ValidationError):
        Settings()


def test_key_is_hidden_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}ALTCHA_HMAC_KEY", TEST_KEY)
    assert TEST_KEY not in repr(Settings())


@pytest.mark.parametrize("value", ["0", "-1", "10000001"])
def test_maxnumber_out_of_range_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(f"{PREFIX}ALTCHA_MAXNUMBER", value)
    with pytest.raises(ValidationError):
        Settings()
