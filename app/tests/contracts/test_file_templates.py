"""Адаптер `FileTemplates`: читає `<корінь>/<область>/<імʼя>.html`, кешує на процес."""

from pathlib import Path

import pytest

from application.ports.templates import TemplateKey, TemplatesUnavailableError
from infrastructure.templates.catalog import FileTemplates

# Кирилиця, CRLF, без фінального переведення рядка: адаптер не нормалізує нічого.
TEXT = "<p>Привіт, світе</p>\r\n<p>другий рядок</p>\n\n<p>останній</p>"


def _suffix(key: TemplateKey) -> str:
    return ".txt" if key.value.startswith("mail/") else ".html"


def _write(root: Path, key: TemplateKey, text: bytes) -> Path:
    path = root / f"{key.value}{_suffix(key)}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text)
    return path


def _write_all(root: Path, text: bytes = TEXT.encode()) -> None:
    for key in TemplateKey:
        _write(root, key, text)


def test_known_key_returns_the_file_text_byte_for_byte(tmp_path: Path) -> None:
    _write_all(tmp_path)

    assert FileTemplates.load(tmp_path).get(TemplateKey.OAUTH_LOGIN) == TEXT


def test_text_is_cached_for_the_process(tmp_path: Path) -> None:
    _write_all(tmp_path)
    templates = FileTemplates.load(tmp_path)

    _write(tmp_path, TemplateKey.OAUTH_LOGIN, b"changed after load")

    assert templates.get(TemplateKey.OAUTH_LOGIN) == TEXT


@pytest.mark.parametrize("key", list(TemplateKey))
def test_missing_file_fails_at_load_and_names_the_file(
    tmp_path: Path, key: TemplateKey
) -> None:
    _write_all(tmp_path)
    (tmp_path / f"{key.value}{_suffix(key)}").unlink()

    with pytest.raises(TemplatesUnavailableError, match=rf"{key.value}\{_suffix(key)}"):
        FileTemplates.load(tmp_path)


def test_file_that_is_not_utf8_fails_at_load_and_names_the_file(tmp_path: Path) -> None:
    _write_all(tmp_path)
    _write(tmp_path, TemplateKey.OAUTH_LOGIN_FORM, b"\xff\xfe\x00broken")

    with pytest.raises(TemplatesUnavailableError, match=r"oauth/login_form\.html"):
        FileTemplates.load(tmp_path)


def test_mail_templates_are_plain_text_files(tmp_path: Path) -> None:
    _write_all(tmp_path)
    _write(tmp_path, TemplateKey.MAIL_SIGNUP_CODE, "Код: $code".encode())

    assert (
        FileTemplates.load(tmp_path).get(TemplateKey.MAIL_SIGNUP_CODE) == "Код: $code"
    )
