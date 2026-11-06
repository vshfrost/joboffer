"""Справжній каталог `app/templates/`: сторінка входу агента у стилі Pine, без скриптів і зовнішніх ресурсів."""

from pathlib import Path

import pytest

from application.ports.templates import TemplateKey
from infrastructure.templates.catalog import FileTemplates

CATALOG = Path(__file__).resolve().parents[2] / "templates"


@pytest.fixture(scope="module")
def templates() -> FileTemplates:
    return FileTemplates.load(CATALOG)


@pytest.mark.parametrize("key", list(TemplateKey))
def test_every_key_has_a_non_empty_file(key: TemplateKey) -> None:
    suffix = ".txt" if key.value.startswith("mail/") else ".html"
    assert (CATALOG / f"{key.value}{suffix}").read_text(encoding="utf-8").strip() != ""


@pytest.mark.parametrize("key", list(TemplateKey))
def test_templates_have_no_scripts_and_no_external_resources(
    templates: FileTemplates, key: TemplateKey
) -> None:
    text = templates.get(key).lower()

    assert "<script" not in text
    assert "http://" not in text
    assert "https://" not in text
    assert "javascript:" not in text


def test_page_shell_is_a_ukrainian_mobile_friendly_pine_page_with_inline_css(
    templates: FileTemplates,
) -> None:
    page = templates.get(TemplateKey.OAUTH_LOGIN)

    assert page.lstrip().lower().startswith("<!doctype html>")
    assert '<html lang="uk">' in page
    assert 'name="viewport"' in page
    assert "<style>" in page
    assert "#356859" in page  # --primary Pine
    assert "$content" in page


def test_form_posts_email_and_password_with_the_request_id(
    templates: FileTemplates,
) -> None:
    form = templates.get(TemplateKey.OAUTH_LOGIN_FORM)

    assert 'method="post"' in form
    assert 'action="login"' in form  # відносна: за Caddy префікс стрипиться
    assert 'name="rid"' in form
    assert 'type="email"' in form
    assert 'name="email"' in form
    assert 'type="password"' in form
    assert 'name="password"' in form
    assert 'autocomplete="current-password"' in form
    for placeholder in ("$rid", "$email", "$client_name", "$redirect_host"):
        assert placeholder in form


def test_form_tells_who_asks_and_where_the_code_goes(templates: FileTemplates) -> None:
    form = templates.get(TemplateKey.OAUTH_LOGIN_FORM)

    assert "$client_name" in form
    assert "$redirect_host" in form


def test_form_leaves_a_place_for_the_google_button(templates: FileTemplates) -> None:
    assert "$google" in templates.get(TemplateKey.OAUTH_LOGIN_FORM)


def test_google_button_goes_through_the_gate_with_the_request_id(
    templates: FileTemplates,
) -> None:
    fragment = templates.get(TemplateKey.OAUTH_LOGIN_GOOGLE)

    assert (
        'href="auth/google/start?rid=$rid"' in fragment
    )  # відносна: за Caddy префікс стрипиться
    assert "Увійти через Google" in fragment
