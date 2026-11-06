"""Режим реєстрації: за замовчуванням closed, дозволені лише closed і invite."""

import pytest
from pydantic import ValidationError

from bootstrap.settings import Settings

URL = "postgresql+psycopg://app:secret-in-test@localhost:5432/app"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOBOFFER_SIGNUP_MODE", raising=False)
    monkeypatch.setenv("JOBOFFER_DATABASE_URL", URL)


def test_signup_is_closed_by_default() -> None:
    assert Settings().signup_mode == "closed"


def test_signup_mode_invite_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOBOFFER_SIGNUP_MODE", "invite")
    assert Settings().signup_mode == "invite"


def test_unknown_signup_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBOFFER_SIGNUP_MODE", "open")
    with pytest.raises(ValidationError):
        Settings()
