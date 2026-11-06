"""Шаблони листів у `app/templates/mail/`: UTF-8 текст, код підставляється, посилань нема."""

from pathlib import Path
from string import Template

from application.ports.templates import TemplateKey
from infrastructure.templates.catalog import FileTemplates

TEMPLATES = Path(__file__).parents[2] / "templates"


def test_signup_code_body_is_a_utf8_text_template_with_only_the_code_placeholder() -> (
    None
):
    text = FileTemplates.load(TEMPLATES).get(TemplateKey.MAIL_SIGNUP_CODE)

    assert (TEMPLATES / "mail" / "signup_code.txt").is_file()
    assert Template(text).get_identifiers() == ["code"]
    assert "Ваш код підтвердження: 483920" in Template(text).substitute(code="483920")


def test_signup_code_subject_is_one_non_empty_cyrillic_line() -> None:
    text = FileTemplates.load(TEMPLATES).get(TemplateKey.MAIL_SIGNUP_CODE_SUBJECT)

    assert text.strip() == "Код підтвердження joboffer"
    assert "\n" not in text.strip()


def test_account_exists_body_is_a_utf8_text_without_placeholders_or_links() -> None:
    text = FileTemplates.load(TEMPLATES).get(TemplateKey.MAIL_ACCOUNT_EXISTS)

    assert (TEMPLATES / "mail" / "account_exists.txt").is_file()
    assert Template(text).get_identifiers() == []
    assert "вже є акаунт" in text
    assert "http" not in text


def test_account_exists_subject_is_one_non_empty_cyrillic_line() -> None:
    text = FileTemplates.load(TEMPLATES).get(TemplateKey.MAIL_ACCOUNT_EXISTS_SUBJECT)

    assert text.strip() == "Акаунт joboffer уже існує"
    assert "\n" not in text.strip()
