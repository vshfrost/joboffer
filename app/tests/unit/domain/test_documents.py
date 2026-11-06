"""Домен документів: рядки з фактами, CV, лист. Ліміти й тексти помилок — як у v1 (`origin/main` `99a2007`)."""

import pytest

from domain.documents.document import (
    MAX_BULLETS,
    MAX_CLAIM_LENGTH,
    MAX_ENTRIES,
    MAX_FACT_IDS,
    MAX_LETTER_FACT_IDS,
    MAX_LETTER_WORDS,
    MAX_SKILL_LABEL,
    MIN_LETTER_WORDS,
    Claim,
    CoverLetter,
    Cv,
    CvEntry,
    CvSection,
    CvSectionName,
    DocumentKind,
)
from domain.shared.errors import InvalidValue

LINE = Claim("Built payment APIs in Python", (1,))


def _words(count: int) -> str:
    return " ".join(["word"] * count)


def test_limits_are_the_v1_limits() -> None:
    assert (
        MAX_CLAIM_LENGTH,
        MAX_FACT_IDS,
        MAX_BULLETS,
        MAX_ENTRIES,
        MIN_LETTER_WORDS,
        MAX_LETTER_WORDS,
        MAX_LETTER_FACT_IDS,
        MAX_SKILL_LABEL,
    ) == (400, 10, 12, 20, 150, 250, 30, 30)


def test_document_kinds_are_stored_as_in_v1() -> None:
    assert [kind.value for kind in DocumentKind] == ["cv", "cl"]


def test_section_names_are_the_ats_headings_of_v1() -> None:
    assert [name.value for name in CvSectionName] == [
        "Experience",
        "Projects",
        "Achievements",
        "Skills",
        "Education",
        "Education and Languages",
        "Certifications",
        "Languages",
    ]


def test_claim_without_fact_ids_is_rejected() -> None:
    with pytest.raises(InvalidValue) as error:
        Claim("Built payment APIs", ())

    assert error.value.message == "Рядок без fact_ids: 'Built payment APIs'."


def test_claim_text_is_one_to_four_hundred_characters() -> None:
    with pytest.raises(InvalidValue) as empty:
        Claim("", (1,))
    with pytest.raises(InvalidValue) as long:
        Claim("x" * (MAX_CLAIM_LENGTH + 1), (1,))

    assert empty.value.message == "Кожен рядок — від 1 до 400 символів: ''."
    assert long.value.message == (f"Кожен рядок — від 1 до 400 символів: {'x' * 60!r}.")
    assert Claim("x" * MAX_CLAIM_LENGTH, (1,)).text == "x" * MAX_CLAIM_LENGTH


def test_claim_has_at_most_ten_fact_ids() -> None:
    with pytest.raises(InvalidValue) as error:
        Claim("Too many", tuple(range(1, MAX_FACT_IDS + 2)))

    assert error.value.message == "Не більше 10 fact_ids на рядок: 'Too many'."
    assert Claim("Ten", tuple(range(1, MAX_FACT_IDS + 1))).fact_ids == tuple(
        range(1, 11)
    )


def test_entry_has_at_most_twelve_bullets() -> None:
    with pytest.raises(InvalidValue) as error:
        CvEntry(LINE, (LINE,) * (MAX_BULLETS + 1))

    assert error.value.message == (
        "Не більше 12 пунктів у 'Built payment APIs in Python'."
    )
    assert len(CvEntry(LINE, (LINE,) * MAX_BULLETS).bullets) == MAX_BULLETS


def test_section_has_one_to_twenty_entries() -> None:
    with pytest.raises(InvalidValue) as none:
        CvSection(CvSectionName.EXPERIENCE, ())
    with pytest.raises(InvalidValue) as many:
        CvSection(CvSectionName.SKILLS, (CvEntry(LINE),) * (MAX_ENTRIES + 1))

    assert none.value.message == "Секція Experience: від 1 до 20 пунктів."
    assert many.value.message == "Секція Skills: від 1 до 20 пунктів."
    assert (
        len(CvSection(CvSectionName.SKILLS, (CvEntry(LINE),) * MAX_ENTRIES).entries)
        == 20
    )


def test_skill_group_label_fits_its_column() -> None:
    label = Claim("x" * (MAX_SKILL_LABEL + 1), (1,))

    with pytest.raises(InvalidValue) as error:
        CvSection(CvSectionName.SKILLS, (CvEntry(label, (LINE,)),))

    assert error.value.message == (
        f"Назва групи скілів — до 30 символів: {'x' * 31!r}."
    )


def test_label_limit_applies_only_to_skill_groups_with_items() -> None:
    label = Claim("x" * (MAX_SKILL_LABEL + 1), (1,))

    # Група без пунктів — рядок на всю ширину; в інших секціях заголовок не обмежено.
    assert CvSection(CvSectionName.SKILLS, (CvEntry(label),)).entries
    assert CvSection(CvSectionName.EXPERIENCE, (CvEntry(label, (LINE,)),)).entries
    assert CvSection(
        CvSectionName.SKILLS,
        (CvEntry(Claim("x" * MAX_SKILL_LABEL, (1,)), (LINE,)),),
    ).entries


def test_cv_needs_sections() -> None:
    with pytest.raises(InvalidValue) as error:
        Cv(LINE, LINE, ())

    assert error.value.message == "CV без секцій."


def test_cv_section_appears_once() -> None:
    skills = CvSection(CvSectionName.SKILLS, (CvEntry(LINE),))

    with pytest.raises(InvalidValue) as error:
        Cv(LINE, LINE, (skills, skills))

    assert error.value.message == "Кожна секція — один раз."


def test_section_headings_in_pdf() -> None:
    assert CvSectionName.EXPERIENCE.heading == "Professional Experience"
    assert CvSectionName.PROJECTS.heading == "Selected Projects"
    assert CvSectionName.SKILLS.heading == "Skills"
    assert CvSectionName.EDUCATION_AND_LANGUAGES.heading == "Education and Languages"


def test_entry_lists_its_claims_in_reading_order() -> None:
    entry = CvEntry(
        Claim("Engineer · Acme", (4,)),
        (Claim("APIs", (5,)), Claim("Queues", (8,))),
        meta=Claim("2021 - 2024", (6,)),
        subtitle=Claim("Payments team of 5", (7,)),
    )

    assert [claim.text for claim in entry.claims()] == [
        "Engineer · Acme",
        "2021 - 2024",
        "Payments team of 5",
        "APIs",
        "Queues",
    ]


def test_entry_without_meta_and_subtitle_lists_heading_and_bullets() -> None:
    entry = CvEntry(Claim("Python", (1,)), (Claim("asyncio", (2,)),))

    assert [claim.text for claim in entry.claims()] == ["Python", "asyncio"]


def test_cv_collects_fact_ids_of_every_line() -> None:
    cv = Cv(
        headline=Claim("Senior Backend Engineer", (1,)),
        summary=Claim("Payments backend", (2, 3)),
        sections=(
            CvSection(
                CvSectionName.EXPERIENCE,
                (
                    CvEntry(
                        Claim("Engineer · Acme", (4,)),
                        (Claim("APIs", (5,)),),
                        meta=Claim("2021 - 2024", (6,)),
                        subtitle=Claim("Payments team of 5", (7,)),
                    ),
                ),
            ),
        ),
    )

    assert cv.fact_ids == {1, 2, 3, 4, 5, 6, 7}
    assert [claim.text for claim in cv.claims()] == [
        "Senior Backend Engineer",
        "Payments backend",
        "Engineer · Acme",
        "2021 - 2024",
        "Payments team of 5",
        "APIs",
    ]


def test_letter_is_one_hundred_fifty_to_two_hundred_fifty_words() -> None:
    for count in (MIN_LETTER_WORDS - 1, MAX_LETTER_WORDS + 1):
        with pytest.raises(InvalidValue) as error:
            CoverLetter((_words(count),), (1,))
        assert error.value.message == f"Лист — 150–250 слів, а тут {count}."

    assert CoverLetter((_words(MIN_LETTER_WORDS),), (1,))
    assert CoverLetter((_words(MAX_LETTER_WORDS),), (1,))


def test_letter_words_are_counted_across_paragraphs() -> None:
    assert CoverLetter((_words(100), _words(50)), (1,))

    with pytest.raises(InvalidValue) as error:
        CoverLetter((_words(100), _words(49)), (1,))
    assert error.value.message == "Лист — 150–250 слів, а тут 149."


@pytest.mark.parametrize("placeholder", ["[Company]", "[Hiring Manager]", "[]"])
def test_letter_with_an_unfilled_template_is_rejected(placeholder: str) -> None:
    body = _words(MIN_LETTER_WORDS)

    with pytest.raises(InvalidValue) as error:
        CoverLetter((f"Dear {placeholder},", body), (1,))

    assert error.value.message == f"Незаповнений шаблон у листі: {placeholder}."


def test_letter_names_the_first_unfilled_template() -> None:
    body = _words(MIN_LETTER_WORDS)

    with pytest.raises(InvalidValue) as error:
        CoverLetter((body, "Hi [Name]", "Bye [Other]"), (1,))

    assert error.value.message == "Незаповнений шаблон у листі: [Name]."


def test_letter_without_fact_ids_is_rejected() -> None:
    with pytest.raises(InvalidValue) as error:
        CoverLetter((_words(MIN_LETTER_WORDS),), ())

    assert error.value.message == (
        "Лист без fact_ids: вкажи факти, на які він спирається."
    )


def test_letter_has_at_most_thirty_fact_ids() -> None:
    with pytest.raises(InvalidValue) as error:
        CoverLetter(
            (_words(MIN_LETTER_WORDS),), tuple(range(1, MAX_LETTER_FACT_IDS + 2))
        )

    assert error.value.message == "Не більше 30 fact_ids у листі."
    assert CoverLetter(
        (_words(MIN_LETTER_WORDS),), tuple(range(1, MAX_LETTER_FACT_IDS + 1))
    )


def test_letter_text_joins_paragraphs_with_a_blank_line() -> None:
    body = _words(MIN_LETTER_WORDS)

    letter = CoverLetter((body, "Best, Alex"), (1,))

    assert letter.text == f"{body}\n\nBest, Alex"


def test_letter_lines_split_a_paragraph_by_single_line_breaks() -> None:
    body = _words(MIN_LETTER_WORDS)

    letter = CoverLetter((body, "Best regards,\nAlex"), (1,))

    assert letter.lines == ((body,), ("Best regards,", "Alex"))
