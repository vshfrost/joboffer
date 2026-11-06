"""Контракти identity: пароль лише в командах і ніколи в repr; результат без секретів."""

from dataclasses import fields
from datetime import UTC, datetime

from application.contracts.identity import Authenticate, CreateUser, UserView

PASSWORD = "correct horse battery"


def test_commands_do_not_show_password_in_repr() -> None:
    assert PASSWORD not in repr(
        CreateUser(email="a@b.co", display_name="A", password=PASSWORD)
    )
    assert PASSWORD not in repr(Authenticate(email="a@b.co", password=PASSWORD))


def test_user_view_has_no_secret_fields() -> None:
    assert {f.name for f in fields(UserView)} == {
        "id",
        "email",
        "display_name",
        "created_at",
    }
    view = UserView(
        id="1",
        email="a@b.co",
        display_name="A",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert "password" not in repr(view)
