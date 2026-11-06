"""Задуманий текст документів у порядку читання (для ATS-lint), шапка з контактів і ім'я файлу."""

from dataclasses import dataclass

from domain.documents.document import (
    CoverLetter,
    Cv,
    CvEntry,
    CvSectionName,
    DocumentKind,
)
from domain.documents.lint import Layout
from domain.profile.contacts import Contacts

MAX_CV_PAGES = 2
MAX_LETTER_PAGES = 1
SUMMARY_HEADING = "Profile"
HTTPS = "https://"
CONTACT_SEPARATOR = " · "
SKILL_SEPARATOR = " · "
FILE_LABELS = {DocumentKind.CV: "CV", DocumentKind.COVER_LETTER: "Cover_Letter"}


@dataclass(frozen=True, slots=True)
class ContactItem:
    """Один контакт у шапці PDF: видимий текст і повне https-посилання (порожнє — просто текст)."""

    text: str
    url: str = ""


def contact_item_rows(contacts: Contacts) -> tuple[tuple[ContactItem, ...], ...]:
    """Рядки контактів у шапці PDF по порядку; порожні поля й рядки пропускаються.
    LinkedIn і GitHub несуть повний URL, інші поля — лише текст."""
    rows = (
        (ContactItem(contacts.city), ContactItem(contacts.work_authorization)),
        (ContactItem(contacts.email), ContactItem(contacts.phone)),
        (_link_item(contacts.linkedin_url), _link_item(contacts.github_url)),
    )
    filled = (tuple(item for item in row if item.text) for row in rows)
    return tuple(row for row in filled if row)


def _link_item(url: str) -> ContactItem:
    return ContactItem(link_text(url), url if url.startswith(HTTPS) else "")


def contact_rows(contacts: Contacts) -> tuple[tuple[str, ...], ...]:
    """Те саме, що `contact_item_rows`, лише тексти."""
    return tuple(
        tuple(item.text for item in row) for row in contact_item_rows(contacts)
    )


def link_text(url: str) -> str:
    """Посилання в шапці так, як у зразку: без https:// і www., «linkedin.com/in/…»."""
    text = url.removeprefix(HTTPS).removeprefix("www.")
    return text.removesuffix("/")


def contact_lines(contacts: Contacts) -> tuple[str, ...]:
    """Контакти в шапці PDF так, як їх читає парсер."""
    return tuple(CONTACT_SEPARATOR.join(row) for row in contact_rows(contacts))


def skill_items(entry: CvEntry) -> str:
    """Пункти групи скілів одним рядком таблиці."""
    return SKILL_SEPARATOR.join(bullet.text for bullet in entry.bullets)


def cv_layout(cv: Cv, contacts: Contacts) -> Layout:
    """Текст CV у порядку читання — так, як його малює шаблон `app/templates/pdf/cv.html`.
    Ім'я й посаду шаблон повторює в шапці з 2-ї сторінки — це колонтитул."""
    lines = [contacts.full_name, cv.headline.text, *contact_lines(contacts)]
    lines += [SUMMARY_HEADING, cv.summary.text]
    for section in cv.sections:
        lines.append(section.name.heading)
        for entry in section.entries:
            if section.name is CvSectionName.SKILLS and entry.bullets:
                lines += [entry.heading.text, skill_items(entry)]
            else:
                lines.extend(claim.text for claim in entry.claims())
    headings = (SUMMARY_HEADING, *(section.name.heading for section in cv.sections))
    furniture = tuple(filter(None, (contacts.full_name, cv.headline.text)))
    return Layout(tuple(filter(None, lines)), headings, MAX_CV_PAGES, furniture)


def cover_letter_layout(letter: CoverLetter, contacts: Contacts) -> Layout:
    """Текст листа в порядку читання — як у шаблоні `app/templates/pdf/cover_letter.html`."""
    lines = [contacts.full_name, *contact_lines(contacts)]
    lines += (line for paragraph in letter.lines for line in paragraph)
    return Layout(tuple(filter(None, lines)), (), MAX_LETTER_PAGES)


def pdf_file_name(full_name: str, kind: DocumentKind) -> str:
    """Назва файлу для рекрутера: «Alex_Example_CV.pdf»; лише ASCII-літери й цифри."""
    words = [
        "".join(c for c in word if c.isascii() and c.isalnum())
        for word in full_name.split()
    ]
    return "_".join([*filter(None, words), FILE_LABELS[kind]]) + ".pdf"
