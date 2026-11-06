"""Шаблони PDF у `app/templates/pdf/`: HTML збігається з рендером v1 (Jinja2, `origin/main` `99a2007`), з фото і без.

Еталон — `tests/support/v1_pdf_html.py`, знятий зі справжнього рендера v1: вигляд документів не змінено;
рамка фото в шапці CV — як у v1 (101 × 113 pt праворуч, відступ тексту).
Екранування — для всього тексту вакансії й claim; сирого HTML у PDF не потрапляє.
"""

import re
from pathlib import Path
from typing import Any

import pytest

from application.ports.templates import TemplateKey
from domain.documents.document import (
    Claim,
    CoverLetter,
    Cv,
    CvEntry,
    CvSection,
    CvSectionName,
)
from domain.profile.contacts import Contacts
from infrastructure.pdf.render import WeasyPrintRenderer
from infrastructure.templates.catalog import FileTemplates
from tests.support.v1_pdf_html import (
    CONTACTS,
    CV,
    LETTER,
    PHOTO,
    V1_CV_HTML,
    V1_CV_HTML_WITH_PHOTO,
    V1_LETTER_HTML,
)

CATALOG = Path(__file__).resolve().parents[2] / "templates"
INLINE = (
    TemplateKey.PDF_CV_PHOTO,
    TemplateKey.PDF_CV_PHOTO_CLASS,
    TemplateKey.PDF_CONTACT_ITEM,
    TemplateKey.PDF_CONTACT_SEPARATOR,
    TemplateKey.PDF_LETTER_BREAK,
)


@pytest.fixture(scope="module")
def renderer() -> WeasyPrintRenderer:
    return WeasyPrintRenderer(FileTemplates.load(CATALOG))


def claim(data: dict[str, Any]) -> Claim:
    return Claim(str(data["text"]), tuple(data["fact_ids"]))


def sample_cv() -> Cv:
    def entry(data: dict[str, Any]) -> CvEntry:
        return CvEntry(
            claim(data["heading"]),
            tuple(claim(b) for b in data["bullets"]),
            claim(data["meta"]) if data.get("meta") else None,
            claim(data["subtitle"]) if data.get("subtitle") else None,
        )

    return Cv(
        claim(CV["headline"]),
        claim(CV["summary"]),
        tuple(
            CvSection(
                CvSectionName(section["name"]),
                tuple(entry(e) for e in section["entries"]),
            )
            for section in CV["sections"]
        ),
    )


def sample_letter() -> CoverLetter:
    return CoverLetter(tuple(LETTER["paragraphs"]), tuple(LETTER["fact_ids"]))


def squeeze(html: str) -> str:
    """Лише пробіли між тегами не мають значення для вигляду; текст і атрибути — точно."""
    return re.sub(r">\s+<", "><", re.sub(r"\s+", " ", html)).strip()


def test_the_cv_html_is_the_html_of_v1(renderer: WeasyPrintRenderer) -> None:
    html = renderer.cv_html(sample_cv(), Contacts(**CONTACTS))

    assert squeeze(html) == squeeze(V1_CV_HTML)


def test_the_cv_html_with_a_photo_is_the_html_of_v1(
    renderer: WeasyPrintRenderer,
) -> None:
    html = renderer.cv_html(sample_cv(), Contacts(**CONTACTS), PHOTO)

    assert squeeze(html) == squeeze(V1_CV_HTML_WITH_PHOTO)


def test_the_photo_is_an_inline_jpeg_in_the_header_and_pushes_the_text_aside(
    renderer: WeasyPrintRenderer,
) -> None:
    html = renderer.cv_html(sample_cv(), Contacts(**CONTACTS), PHOTO)

    assert (
        '<header class="with-photo"><img class="photo" src="data:image/jpeg;base64,'
        in squeeze(html)
    )
    assert html.count("<img ") == 1


def test_a_cv_without_a_photo_has_no_image_and_no_room_kept_for_one(
    renderer: WeasyPrintRenderer,
) -> None:
    html = renderer.cv_html(sample_cv(), Contacts(**CONTACTS), None)

    assert "<img" not in html
    assert 'class="with-photo"' not in html
    assert "<header>" in html


def test_the_cover_letter_never_gets_a_photo(renderer: WeasyPrintRenderer) -> None:
    html = renderer.cover_letter_html(sample_letter(), Contacts(**CONTACTS))

    assert "<img" not in html
    assert "with-photo" not in html


def test_the_cover_letter_html_is_the_html_of_v1(renderer: WeasyPrintRenderer) -> None:
    html = renderer.cover_letter_html(sample_letter(), Contacts(**CONTACTS))

    assert squeeze(html) == squeeze(V1_LETTER_HTML)


def test_cv_html_escapes_text_and_skips_empty_contacts(
    renderer: WeasyPrintRenderer,
) -> None:
    cv = Cv(
        headline=Claim("Backend <Engineer>", (1,)),
        summary=Claim("Payments & cards", (1,)),
        sections=(
            CvSection(
                CvSectionName.SKILLS, (CvEntry(Claim("<script>x</script>", (1,))),)
            ),
        ),
    )

    html = renderer.cv_html(
        cv, Contacts(full_name="Alex Example", email="alex@example.com")
    )

    assert "Backend &lt;Engineer&gt;" in html
    assert "Payments &amp; cards" in html
    assert "<script>" not in html
    assert '<p class="contacts"><span>alex@example.com</span></p>' in html
    assert "<h2>Skills</h2>" in html


def test_a_dollar_sign_in_the_text_is_not_a_template_placeholder(
    renderer: WeasyPrintRenderer,
) -> None:
    cv = Cv(
        headline=Claim("Pays $name $$ and ${summary}", (1,)),
        summary=Claim("Saved $5M", (1,)),
        sections=(
            CvSection(CvSectionName.SKILLS, (CvEntry(Claim("$sections", (1,))),)),
        ),
    )

    html = renderer.cv_html(cv, Contacts(full_name="Alex $contacts"))

    assert "Pays $name $$ and ${summary}" in html
    assert "Saved $5M" in html
    assert ">$sections<" in html
    assert "Alex $contacts" in html


def test_cv_html_has_skills_table_and_entry_meta(renderer: WeasyPrintRenderer) -> None:
    html = renderer.cv_html(sample_cv(), Contacts(**CONTACTS))

    assert (
        "<tr><th>Backend &amp; Architecture</th>"
        "<td>Python (5 years) · FastAPI · PHP · Laravel</td></tr>"
    ) in html
    assert '<td class="meta">Jan 2021 - Dec 2024</td>' in html
    assert '<p class="subtitle">Payments platform · team of six</p>' in html
    assert "<h2>Professional Experience</h2>" in html
    assert "<h2>Education and Languages</h2>" in html
    assert (
        '<p class="contacts"><span>alex@example.com</span><span class="sep">·</span>'
        "<span>+34 600 000 000</span></p>"
    ) in html


def test_cover_letter_html_keeps_line_breaks_inside_a_paragraph_and_escapes(
    renderer: WeasyPrintRenderer,
) -> None:
    letter = CoverLetter(
        (
            " ".join(["word"] * 150),
            "Best regards,\nAlex <b>Example</b>\n<script>x</script>",
        ),
        (1,),
    )

    html = renderer.cover_letter_html(letter, Contacts(full_name="Alex Example"))

    assert html.count("<p>") == 2
    assert (
        "<p>Best regards,<br>Alex &lt;b&gt;Example&lt;/b&gt;<br>"
        "&lt;script&gt;x&lt;/script&gt;</p>" in html
    )
    assert "<b>" not in html
    assert "<script>" not in html


def test_cover_letter_html_has_paragraphs_and_header_contacts(
    renderer: WeasyPrintRenderer,
) -> None:
    letter = CoverLetter(
        (" ".join(["word"] * 150), "Payments & <cards>", "Best regards, Alex"), (1,)
    )

    html = renderer.cover_letter_html(
        letter, Contacts(full_name="Alex Example", city="Valencia, Spain")
    )

    assert html.count("<p>") == 3
    assert "<p>Payments &amp; &lt;cards&gt;</p>" in html
    assert '<p class="contacts"><span>Valencia, Spain</span></p>' in html


@pytest.mark.parametrize("key", INLINE)
def test_inline_fragments_have_no_trailing_newline(key: TemplateKey) -> None:
    text = (CATALOG / f"{key.value}.html").read_text(encoding="utf-8")
    assert text == text.rstrip("\n")


def test_the_cv_template_has_the_v1_photo_frame() -> None:
    text = (CATALOG / "pdf" / "cv.html").read_text(encoding="utf-8")
    assert (
        ".photo { position: absolute; top: 19pt; right: 0; width: 101pt; height: 113pt; }"
        in text
    )
    assert ".with-photo > h1, .with-photo > p { padding-right: 115pt; }" in text


def test_the_page_templates_are_a4_documents_with_the_sample_style() -> None:
    for name, title in (("cv", "CV"), ("cover_letter", "Cover Letter")):
        text = (CATALOG / "pdf" / f"{name}.html").read_text(encoding="utf-8")
        assert text.startswith("<!doctype html>")
        assert "size: A4" in text
        assert '"DejaVu Sans"' in text
        assert "#191919" in text
        assert "#DA9F1A" in text
        assert f"<title>$name — {title}</title>" in text
