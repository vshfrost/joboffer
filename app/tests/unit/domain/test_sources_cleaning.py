"""Очищення вакансії з джерела: невидимі символи, ліміти, один рядок назви, канонічний URL."""

from dataclasses import replace

import pytest

from domain.sources.posting import MAX_TITLE_LENGTH, Posting, sanitize

URL = "https://acme.example/jobs/1"


def raw(**fields: object) -> Posting:
    base: dict[str, object] = {
        "title": "Backend Engineer",
        "url": URL,
        "text": "Build services.",
    }
    return Posting(**(base | fields))  # type: ignore[arg-type]


def clean(**fields: object) -> Posting:
    cleaned = sanitize(raw(**fields))
    assert cleaned is not None
    return cleaned


@pytest.mark.parametrize(
    "invisible", ["\u200b", "\u200e", "\u202e", "\ufeff", "\x00", "\x07", "\u00ad"]
)
def test_invisible_characters_are_stripped_from_the_title(invisible: str) -> None:
    assert clean(title=f"Back{invisible}end").title == "Backend"


def test_invisible_characters_are_stripped_from_the_company() -> None:
    assert clean(company="Ac\u200bme\x00").company == "Acme"


def test_invisible_characters_are_stripped_from_the_text() -> None:
    assert clean(text="Build\u202e services\x00.").text == "Build services."


def test_the_text_keeps_its_line_breaks() -> None:
    assert clean(text="First line\nSecond line").text == "First line\nSecond line"


def test_the_text_collapses_runs_of_blank_lines() -> None:
    assert clean(text="One\n\n\n\nTwo").text == "One\n\nTwo"


def test_the_title_is_one_line() -> None:
    assert (
        clean(title="  Senior\n Python \t Developer  ").title
        == "Senior Python Developer"
    )


def test_the_title_is_cut_to_300_characters() -> None:
    assert len(clean(title="a" * 400).title) == MAX_TITLE_LENGTH == 300


def test_the_company_is_cut_to_200_characters() -> None:
    assert clean(company="c" * 300).company == "c" * 200


def test_the_text_is_cut_to_100000_characters() -> None:
    assert len(clean(text="word " * 50_000).text) <= 100_000


def test_a_text_within_the_limit_is_kept_whole() -> None:
    text = "x" * 100_000
    assert clean(text=text).text == text


def test_the_url_is_canonical() -> None:
    cleaned = clean(url="HTTPS://Acme.Example/jobs/1/?utm_source=feed&id=7#apply")
    assert cleaned.url == "https://acme.example/jobs/1?id=7"


def test_an_empty_company_becomes_none() -> None:
    assert clean(company="  \u200b ").company is None


def test_locations_are_cleaned_one_line_and_deduplicated() -> None:
    cleaned = clean(
        locations=("Madrid,\n Spain", "", "Madrid, Spain", "Va\u200blencia")
    )
    assert cleaned.locations == ("Madrid, Spain", "Valencia")


def test_countries_are_cleaned_like_locations() -> None:
    assert clean(countries=("Spa\u200bin", " ")).countries == ("Spain",)


def test_the_other_fields_are_kept() -> None:
    cleaned = sanitize(raw(work_mode=None, locations_in_text=True))
    assert cleaned is not None
    assert replace(cleaned, locations=(), countries=()) == replace(
        raw(), url=URL, locations_in_text=True
    )


def test_a_posting_without_a_title_is_not_taken() -> None:
    assert sanitize(raw(title="")) is None


def test_a_posting_with_an_invisible_only_title_is_not_taken() -> None:
    assert sanitize(raw(title=" \u200b\n ")) is None


@pytest.mark.parametrize(
    "url", ["", "   ", "not a url", "ftp://acme.example/1", "https://"]
)
def test_a_posting_without_a_usable_url_is_not_taken(url: str) -> None:
    assert sanitize(raw(url=url)) is None


def test_the_display_location_is_the_source_locations() -> None:
    posting = raw(locations=("Madrid", "Valencia"), countries=("Spain",))
    assert posting.location == "Madrid; Valencia"


def test_the_display_location_falls_back_to_the_countries() -> None:
    assert raw(countries=("Spain", "Portugal")).location == "Spain; Portugal"


def test_the_display_location_is_none_when_the_source_gave_none() -> None:
    assert raw().location is None


def test_the_display_location_is_cut_to_300_characters() -> None:
    location = raw(locations=("c" * 400,)).location
    assert location is not None
    assert len(location) == 300
