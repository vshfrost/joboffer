"""Фільтр вакансій з джерел за профілем: назва, формат, локація; формат з тексту; збережені вакансії."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from domain.jobs.ids import JobId
from domain.jobs.job import Job
from domain.profile.locations import Locations, SearchLocation
from domain.profile.modes import WorkMode
from domain.profile.profile import Profile
from domain.profile.rules import Rules
from domain.sources.filtering import Skip, infer_mode, skip_reason, stored_skip_reason
from domain.sources.posting import Posting

REMOTE, HYBRID, ONSITE = WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE


def posting(**fields: object) -> Posting:
    base: dict[str, object] = {
        "title": "Backend Engineer",
        "url": "https://acme.example/jobs/1",
        "text": "Build services.",
    }
    return Posting(**(base | fields))  # type: ignore[arg-type]


def place(name: str, *modes: WorkMode, aliases: tuple[str, ...] = ()) -> SearchLocation:
    return SearchLocation(place=name, aliases=aliases, work_modes=frozenset(modes))


def profile(
    *,
    keywords: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    work_modes: frozenset[WorkMode] = frozenset(),
    places: tuple[SearchLocation, ...] = (),
    include_unknown_mode: bool = True,
) -> Profile:
    return Profile(
        locations=Locations(
            work_modes=work_modes,
            locations=places,
            include_unknown_mode=include_unknown_mode,
        ),
        rules=Rules(title_keywords=keywords, title_exclude=exclude),
    )


# --- порожній текст ------------------------------------------------------------------------


def test_a_posting_without_text_is_empty() -> None:
    assert skip_reason(posting(text=""), profile()) is Skip.EMPTY


def test_an_empty_text_is_reported_before_the_title_rules() -> None:
    assert skip_reason(posting(text=""), profile(keywords=("python",))) is Skip.EMPTY


# --- назва ---------------------------------------------------------------------------------


def test_a_title_without_any_keyword_is_skipped_as_title() -> None:
    result = skip_reason(
        posting(title="Product Manager"), profile(keywords=("python", "backend"))
    )
    assert result is Skip.TITLE


def test_a_title_with_one_of_the_keywords_is_taken() -> None:
    result = skip_reason(posting(), profile(keywords=("python", "backend")))
    assert result is None


def test_a_keyword_phrase_matches_the_title_as_a_whole() -> None:
    result = skip_reason(
        posting(title="Senior Machine Learning Engineer"),
        profile(keywords=("machine learning",)),
    )
    assert result is None


def test_a_keyword_matches_a_whole_word_only() -> None:
    result = skip_reason(
        posting(title="JavaScript Developer"), profile(keywords=("java",))
    )
    assert result is Skip.TITLE


def test_an_excluded_word_in_the_title_is_skipped_as_excluded() -> None:
    result = skip_reason(
        posting(title="Junior Python Developer"), profile(exclude=("junior",))
    )
    assert result is Skip.EXCLUDED


def test_an_excluded_phrase_in_the_title_is_skipped_as_excluded() -> None:
    result = skip_reason(
        posting(title="Python Team Lead"), profile(exclude=("team lead",))
    )
    assert result is Skip.EXCLUDED


def test_an_excluded_word_matches_a_whole_word_only() -> None:
    result = skip_reason(
        posting(title="International Backend Engineer"), profile(exclude=("intern",))
    )
    assert result is None


def test_exclusion_wins_over_a_matching_keyword() -> None:
    result = skip_reason(
        posting(title="Junior Python Developer"),
        profile(keywords=("python",), exclude=("junior",)),
    )
    assert result is Skip.EXCLUDED


@pytest.mark.parametrize(
    ("title", "keyword"),
    [
        ("Back-end Engineer", "back end"),
        ("Back end Engineer", "back-end"),
        ("BACKEND ENGINEER", "backend"),
        ("Backend Engineer", "BACKEND"),
        ("Développeur Backend", "developpeur"),
        ("Developpeur Backend", "Développeur"),
        ("Desarrollador Backend", "DESARROLLADÓR"),
        ("Ingeniero de Datos", "Ingeniéro"),
    ],
)
def test_keywords_ignore_case_hyphens_and_diacritics(title: str, keyword: str) -> None:
    assert skip_reason(posting(title=title), profile(keywords=(keyword,))) is None


def test_exclusion_ignores_hyphens_case_and_diacritics() -> None:
    result = skip_reason(
        posting(title="BACK END Developer"), profile(exclude=("Back-End",))
    )
    assert result is Skip.EXCLUDED


def test_an_empty_profile_takes_any_posting() -> None:
    assert skip_reason(posting(title="Anything at all"), profile()) is None


# --- глобальний формат ---------------------------------------------------------------------


def test_a_mode_outside_the_profile_work_modes_is_skipped_as_format() -> None:
    result = skip_reason(
        posting(work_mode=ONSITE), profile(work_modes=frozenset({REMOTE, HYBRID}))
    )
    assert result is Skip.FORMAT


def test_a_mode_among_the_profile_work_modes_is_taken() -> None:
    result = skip_reason(
        posting(work_mode=HYBRID), profile(work_modes=frozenset({REMOTE, HYBRID}))
    )
    assert result is None


def test_empty_profile_work_modes_restrict_nothing() -> None:
    assert skip_reason(posting(work_mode=ONSITE), profile()) is None


def test_a_mode_in_the_source_location_counts_as_the_posting_mode() -> None:
    result = skip_reason(
        posting(locations=("Madrid (Hybrid)",)), profile(work_modes=frozenset({REMOTE}))
    )
    assert result is Skip.FORMAT


def test_an_unknown_mode_is_not_a_format_mismatch() -> None:
    result = skip_reason(posting(), profile(work_modes=frozenset({REMOTE})))
    assert result is None


def test_the_source_mode_wins_over_the_location_words() -> None:
    result = skip_reason(
        posting(work_mode=REMOTE, locations=("Madrid, hybrid",)),
        profile(work_modes=frozenset({REMOTE})),
    )
    assert result is None


# --- локація -------------------------------------------------------------------------------


def test_empty_profile_locations_restrict_nothing() -> None:
    result = skip_reason(posting(locations=("Tokyo",), work_mode=ONSITE), profile())
    assert result is None


def test_a_location_with_the_place_and_an_allowed_mode_is_taken() -> None:
    result = skip_reason(
        posting(locations=("Valencia, Spain",), work_mode=HYBRID),
        profile(places=(place("Valencia", HYBRID, ONSITE),)),
    )
    assert result is None


def test_a_location_without_the_place_is_skipped_as_location() -> None:
    result = skip_reason(
        posting(locations=("Berlin, Germany",), work_mode=HYBRID),
        profile(places=(place("Valencia", HYBRID),)),
    )
    assert result is Skip.LOCATION


def test_a_posting_without_a_location_is_skipped_as_location() -> None:
    result = skip_reason(
        posting(work_mode=HYBRID), profile(places=(place("Valencia", HYBRID),))
    )
    assert result is Skip.LOCATION


def test_a_synonym_of_the_place_matches() -> None:
    result = skip_reason(
        posting(locations=("Seville, Spain",), work_mode=HYBRID),
        profile(places=(place("Sevilla", HYBRID, aliases=("Seville",)),)),
    )
    assert result is None


def test_a_latin_place_matches_a_whole_word_only() -> None:
    result = skip_reason(
        posting(locations=("Jerome, USA",), work_mode=HYBRID),
        profile(places=(place("Rome", HYBRID),)),
    )
    assert result is Skip.LOCATION


def test_the_place_ignores_case_and_diacritics() -> None:
    result = skip_reason(
        posting(locations=("MÁLAGA, Spain",), work_mode=HYBRID),
        profile(places=(place("Malaga", HYBRID),)),
    )
    assert result is None


@pytest.mark.parametrize("where", ["Україна", "Україні", "Київ, Україні", "України"])
def test_a_cyrillic_place_matches_by_its_stem(where: str) -> None:
    result = skip_reason(
        posting(locations=(where,), work_mode=REMOTE),
        profile(places=(place("Україна", REMOTE),)),
    )
    assert result is None


def test_a_cyrillic_synonym_matches_by_its_stem() -> None:
    result = skip_reason(
        posting(locations=("Київ, Україні",), work_mode=REMOTE),
        profile(places=(place("Ukraine", REMOTE, aliases=("Україна",)),)),
    )
    assert result is None


def test_a_cyrillic_place_does_not_match_another_word() -> None:
    result = skip_reason(
        posting(locations=("Україна",), work_mode=REMOTE),
        profile(places=(place("Угорщина", REMOTE),)),
    )
    assert result is Skip.LOCATION


def test_the_mode_of_another_place_is_skipped_as_location() -> None:
    result = skip_reason(
        posting(locations=("Valencia",), work_mode=REMOTE),
        profile(places=(place("Valencia", HYBRID), place("Madrid", REMOTE))),
    )
    assert result is Skip.LOCATION


def test_the_mode_of_the_matching_place_is_taken() -> None:
    result = skip_reason(
        posting(locations=("Madrid",), work_mode=REMOTE),
        profile(places=(place("Valencia", HYBRID), place("Madrid", REMOTE))),
    )
    assert result is None


def test_an_unknown_mode_follows_include_unknown_mode_when_set() -> None:
    result = skip_reason(
        posting(locations=("Valencia",)),
        profile(places=(place("Valencia", HYBRID),), include_unknown_mode=True),
    )
    assert result is None


def test_an_unknown_mode_follows_include_unknown_mode_when_unset() -> None:
    result = skip_reason(
        posting(locations=("Valencia",)),
        profile(places=(place("Valencia", HYBRID),), include_unknown_mode=False),
    )
    assert result is Skip.LOCATION


def test_the_countries_of_the_source_are_searched_too() -> None:
    result = skip_reason(
        posting(countries=("Spain",), work_mode=REMOTE),
        profile(places=(place("Spain", REMOTE),)),
    )
    assert result is None


def test_a_feed_posting_is_searched_for_the_place_in_title_and_text() -> None:
    result = skip_reason(
        posting(
            title="Backend Engineer, Valencia",
            text="Office in Valencia.",
            work_mode=HYBRID,
            locations_in_text=True,
        ),
        profile(places=(place("Valencia", HYBRID),)),
    )
    assert result is None


def test_a_posting_with_a_structured_location_ignores_the_place_in_its_text() -> None:
    result = skip_reason(
        posting(text="Office in Valencia.", work_mode=HYBRID),
        profile(places=(place("Valencia", HYBRID),)),
    )
    assert result is Skip.LOCATION


# --- формат з тексту -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "mode"),
    [
        ("Fully remote", REMOTE),
        ("Remote (Spain)", REMOTE),
        ("Hybrid, 2 days in the office", HYBRID),
        ("Віддалено", REMOTE),
        ("Дистанційна робота", REMOTE),
        ("Гібридний формат", HYBRID),
        ("Удалённо", REMOTE),
        ("Удаленная работа", REMOTE),
        ("Гибридный график", HYBRID),
        ("Office in Madrid", None),
        ("", None),
    ],
)
def test_the_mode_is_read_from_en_uk_ru_text(text: str, mode: WorkMode | None) -> None:
    assert infer_mode([text]) is mode


@pytest.mark.parametrize(
    "text",
    [
        "Hybrid, occasionally remote",
        "Remote or hybrid",
        "Гібрид, іноді віддалено",
        "Гибрид, иногда удалённо",
    ],
)
def test_hybrid_beats_remote_in_the_text(text: str) -> None:
    assert infer_mode([text]) is HYBRID


def test_the_mode_is_read_across_all_the_given_texts() -> None:
    assert infer_mode(["Madrid", "Remote"]) is REMOTE


# --- збережена вакансія --------------------------------------------------------------------


def stored(**fields: object) -> Job:
    base: dict[str, object] = {
        "id": JobId(UUID(int=1)),
        "number": 1,
        "source": "ats:greenhouse",
        "text": "Build services.",
        "url": "https://acme.example/jobs/1",
        "title": "Backend Engineer",
        "company": "Acme",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "location": "Valencia, Spain",
    }
    return Job(**(base | fields))  # type: ignore[arg-type]


def test_a_stored_job_is_checked_by_the_same_title_rules() -> None:
    result = stored_skip_reason(
        stored(title="Product Manager"), profile(keywords=("python",))
    )
    assert result is Skip.TITLE


def test_a_stored_job_is_checked_by_the_same_location_rules() -> None:
    result = stored_skip_reason(
        stored(location="Berlin"), profile(places=(place("Valencia", HYBRID, ONSITE),))
    )
    assert result is Skip.LOCATION


def test_a_stored_job_that_still_passes_is_taken() -> None:
    result = stored_skip_reason(
        stored(text="Hybrid role."), profile(places=(place("Valencia", HYBRID),))
    )
    assert result is None


def test_a_stored_job_mode_is_read_from_its_text() -> None:
    result = stored_skip_reason(
        stored(text="Fully remote position."),
        profile(work_modes=frozenset({HYBRID, ONSITE})),
    )
    assert result is Skip.FORMAT


def test_a_stored_job_mode_is_read_from_its_location() -> None:
    result = stored_skip_reason(
        stored(location="Valencia (Remote)"),
        profile(places=(place("Valencia", HYBRID),)),
    )
    assert result is Skip.LOCATION


def test_a_stored_job_with_an_unknown_mode_follows_include_unknown_mode() -> None:
    result = stored_skip_reason(
        stored(),
        profile(places=(place("Valencia", HYBRID),), include_unknown_mode=False),
    )
    assert result is Skip.LOCATION


def test_a_stored_feed_job_is_searched_for_the_place_in_its_text() -> None:
    result = stored_skip_reason(
        stored(source="rss:dou", location=None, text="Hybrid role in Valencia."),
        profile(places=(place("Valencia", HYBRID),)),
    )
    assert result is None


def test_a_stored_feed_job_without_the_place_anywhere_is_skipped_as_location() -> None:
    result = stored_skip_reason(
        stored(source="rss:dou", location=None, text="Hybrid role in Berlin."),
        profile(places=(place("Valencia", HYBRID),)),
    )
    assert result is Skip.LOCATION


def test_a_stored_ats_job_without_location_is_checked_by_the_title_rules_only() -> None:
    result = stored_skip_reason(
        stored(location=None, text="Onsite in Berlin."),
        profile(
            keywords=("backend",),
            work_modes=frozenset({REMOTE}),
            places=(place("Valencia", REMOTE),),
        ),
    )
    assert result is None


def test_a_stored_ats_job_without_location_still_fails_the_title_rules() -> None:
    result = stored_skip_reason(stored(location=None), profile(exclude=("backend",)))
    assert result is Skip.EXCLUDED
