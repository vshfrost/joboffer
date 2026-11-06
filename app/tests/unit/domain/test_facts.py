"""Факт, оригінал CV, порядок і лічильники бібліотеки."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from domain.facts.fact import (
    MAX_CV_LENGTH,
    MAX_FACT_LENGTH,
    MAX_FILE_NAME_LENGTH,
    Fact,
    FactKind,
    NewFact,
    NewOriginalCv,
)
from domain.facts.ids import FactId
from domain.facts.library import FactCounts, KindCount, count_facts, ordered
from domain.shared.errors import InvalidValue

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def fact(number: int, kind: FactKind, *, confirmed: bool = False) -> Fact:
    return Fact(
        FactId(UUID(int=number)), number, kind, f"fact {number}", confirmed, NOW, NOW
    )


def test_kinds_follow_the_section_order() -> None:
    assert [kind.value for kind in FactKind] == [
        "experience",
        "achievement",
        "project",
        "skill",
        "education",
        "language",
    ]


def test_fact_text_is_collapsed_to_one_line_and_numbers_are_kept() -> None:
    parsed = NewFact.parse(
        kind="achievement", text="  Cut p95 latency\n by 40%  (1.2s → 0.7s) "
    )
    assert parsed == NewFact(
        FactKind.ACHIEVEMENT, "Cut p95 latency by 40% (1.2s → 0.7s)"
    )


def test_fact_fingerprint_ignores_case_whitespace_and_kind() -> None:
    a = NewFact.parse(kind="skill", text="Python  3.14")
    b = NewFact.parse(kind="experience", text="python 3.14")
    assert a.fingerprint == b.fingerprint
    assert a.fingerprint != NewFact.parse(kind="skill", text="Python 3.13").fingerprint


@pytest.mark.parametrize(
    ("kind", "text", "field", "message"),
    [
        ("hobby", "Chess", "kind", "Невідомий вид факту: 'hobby'."),
        ("skill", " \n ", "text", "Факт не може бути порожнім."),
        (
            "skill",
            "x" * (MAX_FACT_LENGTH + 1),
            "text",
            "Факт задовгий: більше 500 символів — розбий на кілька.",
        ),
    ],
)
def test_an_invalid_fact_is_rejected_with_the_v1_text(
    kind: str, text: str, field: str, message: str
) -> None:
    with pytest.raises(InvalidValue) as raised:
        NewFact.parse(kind=kind, text=text)
    assert (raised.value.field, raised.value.message) == (field, message)


def test_a_fact_at_the_max_length_is_accepted() -> None:
    parsed = NewFact.parse(kind="skill", text="x" * MAX_FACT_LENGTH)
    assert len(parsed.text) == MAX_FACT_LENGTH


def test_the_original_cv_is_trimmed_and_an_empty_file_name_becomes_none() -> None:
    cv = NewOriginalCv.parse(
        text="\n Taras Prykladenko\nSenior Backend \n", file_name=" "
    )
    assert cv == NewOriginalCv(text="Taras Prykladenko\nSenior Backend", file_name=None)
    assert NewOriginalCv.parse(text="CV", file_name=" cv.pdf ").file_name == "cv.pdf"


@pytest.mark.parametrize(
    ("text", "file_name", "field", "message"),
    [
        ("  ", "cv.pdf", "text", "Текст CV порожній."),
        (
            "x" * (MAX_CV_LENGTH + 1),
            "cv.pdf",
            "text",
            "CV задовге: більше 50000 символів.",
        ),
        (
            "CV",
            "x" * (MAX_FILE_NAME_LENGTH + 1),
            "file_name",
            "Назва файлу задовга: більше 255 символів.",
        ),
    ],
)
def test_an_invalid_original_cv_is_rejected_with_the_v1_text(
    text: str, file_name: str, field: str, message: str
) -> None:
    with pytest.raises(InvalidValue) as raised:
        NewOriginalCv.parse(text=text, file_name=file_name)
    assert (raised.value.field, raised.value.message) == (field, message)


def test_the_original_cv_at_the_max_length_is_accepted() -> None:
    assert len(NewOriginalCv.parse(text="x" * MAX_CV_LENGTH, file_name="").text) == (
        MAX_CV_LENGTH
    )


def test_facts_are_ordered_by_kind_then_by_number() -> None:
    facts = [
        fact(1, FactKind.SKILL),
        fact(2, FactKind.ACHIEVEMENT),
        fact(3, FactKind.EXPERIENCE),
        fact(4, FactKind.SKILL),
    ]
    assert [item.number for item in ordered(facts)] == [3, 2, 1, 4]


def test_counts_cover_every_kind_in_section_order_with_status_split() -> None:
    facts = [
        fact(1, FactKind.SKILL, confirmed=True),
        fact(2, FactKind.SKILL),
        fact(3, FactKind.EXPERIENCE),
    ]
    assert count_facts(facts) == FactCounts(
        total=3,
        confirmed=1,
        unconfirmed=2,
        kinds=(
            KindCount(FactKind.EXPERIENCE, 1, 0, 1),
            KindCount(FactKind.ACHIEVEMENT, 0, 0, 0),
            KindCount(FactKind.PROJECT, 0, 0, 0),
            KindCount(FactKind.SKILL, 2, 1, 1),
            KindCount(FactKind.EDUCATION, 0, 0, 0),
            KindCount(FactKind.LANGUAGE, 0, 0, 0),
        ),
    )


def test_no_facts_gives_zero_counts() -> None:
    counts = count_facts([])
    assert (counts.total, counts.confirmed, counts.unconfirmed) == (0, 0, 0)
    assert len(counts.kinds) == 6
