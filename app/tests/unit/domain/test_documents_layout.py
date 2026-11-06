"""Шапка з контактів, задуманий текст документів для lint і ім'я файлу PDF. Поведінка — як у v1 (`origin/main` `99a2007`)."""

import pytest

from domain.documents.document import (
    MIN_LETTER_WORDS,
    Claim,
    CoverLetter,
    Cv,
    CvEntry,
    CvSection,
    CvSectionName,
    DocumentKind,
)
from domain.documents.layout import (
    MAX_CV_PAGES,
    MAX_LETTER_PAGES,
    contact_lines,
    contact_rows,
    cover_letter_layout,
    cv_layout,
    link_text,
    pdf_file_name,
    skill_items,
)
from domain.profile.contacts import Contacts
from domain.shared.errors import InvalidValue

LINE = Claim("Built payment APIs in Python", (1,))


@pytest.mark.parametrize(
    ("full_name", "expected"),
    [
        ("Alex Example", "Alex_Example_CV.pdf"),
        ("  Богдан   O'Neil ", "ONeil_CV.pdf"),
        ("", "CV.pdf"),
    ],
)
def test_pdf_file_name_is_ascii(full_name: str, expected: str) -> None:
    assert pdf_file_name(full_name, DocumentKind.CV) == expected


def test_pdf_file_name_of_cover_letter() -> None:
    assert (
        pdf_file_name("Alex Example", DocumentKind.COVER_LETTER)
        == "Alex_Example_Cover_Letter.pdf"
    )


def test_page_limits_are_the_v1_limits() -> None:
    assert (MAX_CV_PAGES, MAX_LETTER_PAGES) == (2, 1)


@pytest.mark.parametrize(
    ("url", "text"),
    [
        ("https://www.linkedin.com/in/example/", "linkedin.com/in/example"),
        ("https://github.com/example", "github.com/example"),
        ("", ""),
    ],
)
def test_link_text_drops_the_scheme_www_and_trailing_slash(url: str, text: str) -> None:
    assert link_text(url) == text


def test_contact_rows_group_fields_and_skip_empty_ones() -> None:
    contacts = Contacts(
        full_name="Alex Example",
        email="alex@example.com",
        phone="+34 600 000 000",
        city="Valencia, Spain",
        linkedin_url="https://www.linkedin.com/in/example/",
        github_url="https://github.com/example",
        work_authorization="Spain / EU work authorization",
    )

    assert contact_rows(contacts) == (
        ("Valencia, Spain", "Spain / EU work authorization"),
        ("alex@example.com", "+34 600 000 000"),
        ("linkedin.com/in/example", "github.com/example"),
    )
    assert contact_lines(contacts) == (
        "Valencia, Spain · Spain / EU work authorization",
        "alex@example.com · +34 600 000 000",
        "linkedin.com/in/example · github.com/example",
    )


def test_contact_lines_skip_empty_fields_and_rows() -> None:
    assert contact_lines(
        Contacts(city="Valencia", github_url="https://github.com/x")
    ) == ("Valencia", "github.com/x")
    assert contact_lines(Contacts(phone="+34 600 000 000")) == ("+34 600 000 000",)
    assert contact_lines(Contacts(full_name="Alex Example")) == ()


def test_skill_items_are_joined_into_one_cell() -> None:
    entry = CvEntry(
        Claim("Backend", (1,)),
        (Claim("Python", (1,)), Claim("FastAPI", (1,)), Claim("Django", (1,))),
    )
    assert skill_items(entry) == "Python · FastAPI · Django"


def test_cv_layout_follows_the_template_order() -> None:
    cv = Cv(
        headline=Claim("Senior Backend Engineer", (1,)),
        summary=Claim("Payments backend", (1,)),
        sections=(
            CvSection(
                CvSectionName.SKILLS,
                (
                    CvEntry(
                        Claim("Backend", (1,)),
                        (Claim("Python", (1,)), Claim("FastAPI · Django", (1,))),
                    ),
                    CvEntry(Claim("Cloud: AWS, GCP", (1,))),
                ),
            ),
            CvSection(
                CvSectionName.EXPERIENCE,
                (
                    CvEntry(
                        Claim("Engineer · Acme", (1,)),
                        (LINE,),
                        meta=Claim("2021 - 2024", (1,)),
                        subtitle=Claim("Payments team", (1,)),
                    ),
                    CvEntry(Claim("Developer · Beta", (1,)), (LINE,)),
                ),
            ),
        ),
    )

    layout = cv_layout(cv, Contacts(full_name="Alex Example", city="Valencia"))

    assert layout.lines == (
        "Alex Example",
        "Senior Backend Engineer",
        "Valencia",
        "Profile",
        "Payments backend",
        "Skills",
        "Backend",
        "Python · FastAPI · Django",
        "Cloud: AWS, GCP",
        "Professional Experience",
        "Engineer · Acme",
        "2021 - 2024",
        "Payments team",
        "Built payment APIs in Python",
        "Developer · Beta",
        "Built payment APIs in Python",
    )
    assert layout.headings == ("Profile", "Skills", "Professional Experience")
    assert layout.max_pages == MAX_CV_PAGES
    assert layout.furniture == ("Alex Example", "Senior Backend Engineer")


def test_cover_letter_layout_has_name_contacts_and_every_line_of_every_paragraph() -> (
    None
):
    letter = CoverLetter(
        (" ".join(["word"] * MIN_LETTER_WORDS), "Best regards,\nAlex Example"), (1,)
    )

    layout = cover_letter_layout(
        letter, Contacts(full_name="Alex Example", city="Valencia")
    )

    assert layout.lines == (
        "Alex Example",
        "Valencia",
        " ".join(["word"] * MIN_LETTER_WORDS),
        "Best regards,",
        "Alex Example",
    )
    assert layout.headings == ()
    assert layout.max_pages == MAX_LETTER_PAGES
    assert layout.furniture == ()


def test_line_breaks_inside_a_paragraph_do_not_change_the_word_count() -> None:
    assert CoverLetter(("word\n" * (MIN_LETTER_WORDS - 1) + "word",), (1,))
    with pytest.raises(InvalidValue, match="слів"):
        CoverLetter(("word\n" * (MIN_LETTER_WORDS - 2) + "word",), (1,))
