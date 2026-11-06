"""WeasyPrint-рендер CV і листа з HTML-шаблонів `app/templates/pdf/`.

Стиль зразка: темна шапка із золотою смугою, одна колонка тексту, справжній текстовий шар;
шрифти WeasyPrint вбудовує. Кожне значення з даних (текст claim, ім'я, контакти) екранується
й підставляється в шаблон як значення, тож сирого HTML у PDF не потрапляє, а `$` у тексті не є
плейсхолдером. LinkedIn і GitHub у шапці та `https://`-посилання в рядках CV і абзацах листа стають
активними (`<a href>`); видимий текст, його екранування й текстовий шар PDF лишаються як були.
"""

import asyncio
import re
from base64 import b64encode
from collections.abc import Iterable
from html import escape
from string import Template

from application.ports.templates import TemplateKey, Templates
from domain.documents.document import CoverLetter, Cv, CvEntry, CvSection, CvSectionName
from domain.documents.layout import (
    SUMMARY_HEADING,
    ContactItem,
    contact_item_rows,
    skill_items,
)
from domain.profile.contacts import Contacts

# Лише https. Кінець посилання — не розділовий знак: «…/repo.» чи «(…/repo)» не втягують крапку й дужку.
_HTTPS_URL = re.compile(r"https://[^\s<>\"']*[^\s<>\"'.,;:!?)\]]")


def pdf_from_html(html: str) -> bytes:
    # Імпорт тут: WeasyPrint вантажить pango під час імпорту, а він є лише в образі й CI
    # (там, де pango нема, мають проходити тести, що не рендерять PDF).
    from weasyprint import HTML  # noqa: PLC0415

    pdf: bytes = HTML(string=html).write_pdf()
    return pdf


class WeasyPrintRenderer:
    def __init__(self, templates: Templates) -> None:
        self._templates = templates

    def cv_html(self, cv: Cv, contacts: Contacts, photo: bytes | None = None) -> str:
        return self._fill(
            TemplateKey.PDF_CV,
            name=escape(contacts.full_name),
            headline=escape(cv.headline.text),
            contacts=self._contacts(contacts),
            summary_heading=escape(SUMMARY_HEADING),
            summary=self._text(cv.summary.text),
            sections="".join(self._section(section) for section in cv.sections),
            photo_class=""
            if photo is None
            else self._templates.get(TemplateKey.PDF_CV_PHOTO_CLASS),
            photo=""
            if photo is None
            else self._fill(
                TemplateKey.PDF_CV_PHOTO, data=b64encode(photo).decode("ascii")
            ),
        )

    def cover_letter_html(self, letter: CoverLetter, contacts: Contacts) -> str:
        return self._fill(
            TemplateKey.PDF_COVER_LETTER,
            name=escape(contacts.full_name),
            contacts=self._contacts(contacts),
            paragraphs="".join(
                self._fill(
                    TemplateKey.PDF_LETTER_PARAGRAPH,
                    lines=self._join(
                        TemplateKey.PDF_LETTER_BREAK, map(self._text, paragraph)
                    ),
                )
                for paragraph in letter.lines
            ),
        )

    async def render_cv(
        self, cv: Cv, contacts: Contacts, photo: bytes | None = None
    ) -> bytes:
        return await asyncio.to_thread(pdf_from_html, self.cv_html(cv, contacts, photo))

    async def render_cover_letter(
        self, letter: CoverLetter, contacts: Contacts
    ) -> bytes:
        return await asyncio.to_thread(
            pdf_from_html, self.cover_letter_html(letter, contacts)
        )

    # --- шапка ----------------------------------------------------------------------

    def _contacts(self, contacts: Contacts) -> str:
        return "".join(
            self._fill(
                TemplateKey.PDF_CONTACTS_ROW,
                items=self._join(
                    TemplateKey.PDF_CONTACT_SEPARATOR,
                    (
                        self._fill(
                            TemplateKey.PDF_CONTACT_ITEM, text=self._contact(item)
                        )
                        for item in row
                    ),
                ),
            )
            for row in contact_item_rows(contacts)
        )

    def _contact(self, item: ContactItem) -> str:
        if not item.url:
            return escape(item.text)
        return self._link(item.url, item.text)

    # --- секції CV ------------------------------------------------------------------

    def _section(self, section: CvSection) -> str:
        if section.name is CvSectionName.SKILLS:
            body = self._fill(
                TemplateKey.PDF_CV_SKILLS,
                rows="".join(self._skill_row(entry) for entry in section.entries),
            )
        else:
            body = "".join(self._entry(entry) for entry in section.entries)
        return self._fill(
            TemplateKey.PDF_CV_SECTION,
            heading=escape(section.name.heading),
            body=body,
        )

    def _skill_row(self, entry: CvEntry) -> str:
        if entry.bullets:
            return self._fill(
                TemplateKey.PDF_CV_SKILL_ROW,
                label=self._text(entry.heading.text),
                items=self._text(skill_items(entry)),
            )
        return self._fill(
            TemplateKey.PDF_CV_SKILL_LINE, text=self._text(entry.heading.text)
        )

    def _entry(self, entry: CvEntry) -> str:
        heading = self._text(entry.heading.text)
        if not (entry.bullets or entry.meta or entry.subtitle):
            return self._fill(TemplateKey.PDF_CV_LINE, text=heading)
        return self._fill(
            TemplateKey.PDF_CV_ENTRY,
            heading=heading,
            meta=""
            if entry.meta is None
            else self._fill(
                TemplateKey.PDF_CV_ENTRY_META, text=self._text(entry.meta.text)
            ),
            subtitle=""
            if entry.subtitle is None
            else self._fill(
                TemplateKey.PDF_CV_ENTRY_SUBTITLE, text=self._text(entry.subtitle.text)
            ),
            bullets=""
            if not entry.bullets
            else self._fill(
                TemplateKey.PDF_CV_BULLETS,
                items="".join(
                    self._fill(TemplateKey.PDF_CV_BULLET, text=self._text(bullet.text))
                    for bullet in entry.bullets
                ),
            ),
        )

    # --- посилання --------------------------------------------------------------------

    def _text(self, value: str) -> str:
        """Екранований текст, у якому кожне https-посилання — активне."""
        parts: list[str] = []
        end = 0
        for found in _HTTPS_URL.finditer(value):
            parts.append(escape(value[end : found.start()]))
            parts.append(self._link(found.group(), found.group()))
            end = found.end()
        parts.append(escape(value[end:]))
        return "".join(parts)

    def _link(self, url: str, text: str) -> str:
        return self._fill(TemplateKey.PDF_LINK, url=escape(url), text=escape(text))

    # --- підстановка ------------------------------------------------------------------

    def _fill(self, key: TemplateKey, **values: str) -> str:
        """Усі значення вже екрановані; шаблон лише розставляє їх."""
        return Template(self._templates.get(key)).substitute(values)

    def _join(self, separator: TemplateKey, parts: Iterable[str]) -> str:
        return self._templates.get(separator).join(parts)
