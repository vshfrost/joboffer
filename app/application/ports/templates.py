"""Порт каталогу шаблонів (HTML, PDF). Файли лежать у `app/templates/`, а не в коді."""

from enum import StrEnum
from typing import Protocol


class TemplateKey(StrEnum):
    """Значення — шлях `<область>/<імʼя>` до файлу без розширення."""

    OAUTH_LOGIN = "oauth/login"
    OAUTH_LOGIN_FORM = "oauth/login_form"
    OAUTH_LOGIN_EXPIRED = "oauth/login_expired"
    OAUTH_LOGIN_GOOGLE = "oauth/login_google"
    MAIL_SIGNUP_CODE = "mail/signup_code"
    MAIL_SIGNUP_CODE_SUBJECT = "mail/signup_code_subject"
    MAIL_ACCOUNT_EXISTS = "mail/account_exists"
    MAIL_ACCOUNT_EXISTS_SUBJECT = "mail/account_exists_subject"
    PDF_CV = "pdf/cv"
    PDF_CV_BULLET = "pdf/cv_bullet"
    PDF_CV_BULLETS = "pdf/cv_bullets"
    PDF_CV_ENTRY = "pdf/cv_entry"
    PDF_CV_ENTRY_META = "pdf/cv_entry_meta"
    PDF_CV_ENTRY_SUBTITLE = "pdf/cv_entry_subtitle"
    PDF_CV_LINE = "pdf/cv_line"
    PDF_CV_PHOTO = "pdf/cv_photo"
    PDF_CV_PHOTO_CLASS = "pdf/cv_photo_class"
    PDF_CV_SECTION = "pdf/cv_section"
    PDF_CV_SKILL_LINE = "pdf/cv_skill_line"
    PDF_CV_SKILL_ROW = "pdf/cv_skill_row"
    PDF_CV_SKILLS = "pdf/cv_skills"
    PDF_CONTACT_ITEM = "pdf/contact_item"
    PDF_CONTACT_SEPARATOR = "pdf/contact_separator"
    PDF_CONTACTS_ROW = "pdf/contacts_row"
    PDF_COVER_LETTER = "pdf/cover_letter"
    PDF_LETTER_BREAK = "pdf/letter_break"
    PDF_LETTER_PARAGRAPH = "pdf/letter_paragraph"


class TemplatesUnavailableError(Exception):
    """Шаблон не вдалося прочитати: файлу нема або він не UTF-8. Повідомлення називає файл."""


class Templates(Protocol):
    def get(self, key: TemplateKey) -> str:
        """Текст шаблону дослівно, як у файлі."""
        ...
