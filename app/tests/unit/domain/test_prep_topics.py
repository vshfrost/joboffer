"""Теми підготовки: розбір і межі полів, унікальність slug, пріоритет та порядок.

Тексти помилок і ліміти — як у v1 (`origin/main` `99a2007`, `core/domain/prep.py`).
"""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from domain.prep.ids import TopicId
from domain.prep.topic import (
    MAX_GAP_LENGTH,
    MAX_SLUG_LENGTH,
    MAX_SUMMARY_LENGTH,
    MAX_TITLE_LENGTH,
    MAX_TOPICS_PER_SAVE,
    MIN_SLUG_LENGTH,
    NewTopic,
    PrepTopic,
    TopicJob,
    TopicKind,
    by_priority,
    check_unique_slugs,
    parse_gap,
)
from domain.shared.errors import InvalidValue

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
SLUG_MESSAGE = (
    "slug {slug!r}: латиниця в нижньому регістрі, цифри й дефіси між словами, "
    "2–60 символів (напр. mysql-query-optimization)."
)


def parse(**fields: str) -> NewTopic:
    values = {
        "slug": "mysql-query-optimization",
        "title": "Оптимізація запитів MySQL",
        "kind": "tech",
        "summary": "",
        "deadline": "",
    } | fields
    return NewTopic.parse(**values)


def test_limits_are_the_v1_ones() -> None:
    assert (
        MIN_SLUG_LENGTH,
        MAX_SLUG_LENGTH,
        MAX_TITLE_LENGTH,
        MAX_SUMMARY_LENGTH,
        MAX_GAP_LENGTH,
        MAX_TOPICS_PER_SAVE,
    ) == (2, 60, 120, 1000, 300, 20)


def test_kinds_are_tech_behavioral_domain() -> None:
    assert [kind.value for kind in TopicKind] == ["tech", "behavioral", "domain"]


def test_a_valid_topic_is_parsed_with_all_its_fields() -> None:
    topic = parse(
        slug="star-conflict",
        title="Конфлікт у команді",
        kind="behavioral",
        summary="Історія за STAR.",
        deadline="2026-03-15",
    )
    assert topic == NewTopic(
        "star-conflict",
        "Конфлікт у команді",
        TopicKind.BEHAVIORAL,
        "Історія за STAR.",
        date(2026, 3, 15),
    )


def test_summary_and_deadline_are_optional() -> None:
    topic = parse()
    assert (topic.summary, topic.deadline) == ("", None)


@pytest.mark.parametrize(
    "slug", ["go", "mysql-query-optimization", "a1-b2-c3", "42", "a" * 60]
)
def test_a_slug_of_lowercase_latin_digits_and_inner_hyphens_is_valid(
    slug: str,
) -> None:
    assert parse(slug=slug).slug == slug


@pytest.mark.parametrize(
    "slug",
    [
        "MySQL",
        "my_sql",
        "my sql",
        "-mysql",
        "mysql-",
        "my--sql",
        "базa-даних",
        "a",
        "",
        "a" * 61,
    ],
)
def test_a_bad_slug_is_rejected_with_an_example(slug: str) -> None:
    with pytest.raises(InvalidValue) as error:
        parse(slug=slug)
    assert error.value.message == SLUG_MESSAGE.format(slug=slug)


def test_a_slug_is_trimmed_before_the_check() -> None:
    assert parse(slug="  go-concurrency ").slug == "go-concurrency"


def test_a_title_is_one_line() -> None:
    assert parse(title="  Оптимізація \n запитів  ").title == "Оптимізація запитів"


@pytest.mark.parametrize("title", ["", "   ", "т" * 121])
def test_a_title_outside_1_to_120_is_rejected(title: str) -> None:
    with pytest.raises(InvalidValue) as error:
        parse(title=title)
    assert error.value.message == (
        "mysql-query-optimization: назва — від 1 до 120 символів."
    )


def test_a_title_of_120_characters_is_valid() -> None:
    assert len(parse(title="т" * 120).title) == 120


def test_a_summary_over_1000_characters_is_rejected() -> None:
    with pytest.raises(InvalidValue) as error:
        parse(summary="о" * 1001)
    assert error.value.message == "mysql-query-optimization: опис — до 1000 символів."


def test_a_summary_of_1000_characters_is_valid() -> None:
    assert len(parse(summary="о" * 1000).summary) == 1000


@pytest.mark.parametrize("kind", ["Tech", " behavioral ", "DOMAIN"])
def test_a_kind_is_case_and_space_insensitive(kind: str) -> None:
    assert parse(kind=kind).kind.value == kind.strip().lower()


@pytest.mark.parametrize("kind", ["", "soft", "tech;domain"])
def test_an_unknown_kind_is_rejected_listing_the_allowed_ones(kind: str) -> None:
    with pytest.raises(InvalidValue) as error:
        parse(kind=kind)
    assert error.value.message == (
        f"mysql-query-optimization: kind {kind!r} — допустимо tech, behavioral, domain."
    )


@pytest.mark.parametrize(
    "deadline", ["15.03.2026", "2026-3-15", "2026-13-01", "2026-02-30", "завтра"]
)
def test_a_deadline_that_is_not_an_iso_date_is_rejected(deadline: str) -> None:
    with pytest.raises(InvalidValue) as error:
        parse(deadline=deadline)
    assert error.value.message == (
        f"mysql-query-optimization: deadline {deadline!r} — дата YYYY-MM-DD або порожньо."
    )


@pytest.mark.parametrize("deadline", ["", "   "])
def test_an_empty_deadline_means_none(deadline: str) -> None:
    assert parse(deadline=deadline).deadline is None


def test_a_gap_is_one_line() -> None:
    assert parse_gap("go", "  немає \n досвіду   з Go ") == "немає досвіду з Go"


@pytest.mark.parametrize("gap", ["", "  \n ", "г" * 301])
def test_a_gap_outside_1_to_300_is_rejected(gap: str) -> None:
    with pytest.raises(InvalidValue) as error:
        parse_gap("go", gap)
    assert error.value.message == "go: gap — від 1 до 300 символів."


def test_a_gap_of_300_characters_is_valid() -> None:
    assert len(parse_gap("go", "г" * 300)) == 300


def test_distinct_slugs_pass() -> None:
    check_unique_slugs(["go", "rust", "sql"])


def test_a_repeated_slug_is_rejected() -> None:
    with pytest.raises(InvalidValue) as error:
        check_unique_slugs(["go", "rust", "go"])
    assert error.value.message == "Тема go у списку двічі."


def topic(
    number: int,
    *scores: int,
    deadline: date | None = None,
) -> PrepTopic:
    return PrepTopic(
        id=TopicId(UUID(int=number)),
        number=number,
        slug=f"topic-{number}",
        title=f"Тема {number}",
        kind=TopicKind.TECH,
        summary="",
        deadline=deadline,
        created_at=NOW + timedelta(minutes=number),
        jobs=tuple(
            TopicJob(index + 1, None, None, score, "gap")
            for index, score in enumerate(scores)
        ),
    )


def test_priority_is_the_sum_of_the_linked_jobs_scores() -> None:
    assert topic(1, 80, 55, 7).priority == 142


def test_a_topic_without_jobs_has_zero_priority() -> None:
    assert topic(1).priority == 0


def test_higher_priority_goes_first() -> None:
    ordered = by_priority([topic(1, 40), topic(2, 90), topic(3, 30, 30, 40)])
    assert [item.number for item in ordered] == [3, 2, 1]


def test_two_mid_jobs_can_outweigh_one_strong_job() -> None:
    ordered = by_priority([topic(1, 90), topic(2, 50, 50)])
    assert [item.number for item in ordered] == [2, 1]


def test_equal_priority_goes_by_the_closer_deadline() -> None:
    ordered = by_priority(
        [
            topic(1, 70, deadline=date(2026, 5, 1)),
            topic(2, 70, deadline=date(2026, 3, 1)),
        ]
    )
    assert [item.number for item in ordered] == [2, 1]


def test_equal_priority_puts_a_topic_without_a_deadline_lower() -> None:
    ordered = by_priority([topic(1, 70), topic(2, 70, deadline=date(2030, 1, 1))])
    assert [item.number for item in ordered] == [2, 1]


def test_equal_priority_and_deadline_goes_by_the_older_topic() -> None:
    ordered = by_priority([topic(3, 70), topic(1, 70), topic(2, 70)])
    assert [item.number for item in ordered] == [1, 2, 3]


def test_a_deadline_does_not_beat_a_higher_priority() -> None:
    ordered = by_priority([topic(1, 60, deadline=date(2026, 1, 2)), topic(2, 61)])
    assert [item.number for item in ordered] == [2, 1]
