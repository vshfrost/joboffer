"""Аналіз вакансії: розбір і ліміти, фільтри профілю, значення рубрики — тексти як у v1 (`99a2007`)."""

from typing import Any

import pytest

from domain.analysis.analysis import Gap, JobAnalysis, apply_filters
from domain.analysis.keywords import KeywordFacts
from domain.analysis.rubric import NEUTRAL_CANDIDATE, rubric_values
from domain.profile.contacts import Contacts
from domain.profile.locations import Locations
from domain.profile.modes import Seniority, WorkMode
from domain.profile.profile import Profile
from domain.profile.rules import Rules
from domain.profile.target import Target
from domain.shared.errors import InvalidValue


def parse(**fields: Any) -> JobAnalysis:
    base: dict[str, Any] = {"score": 70, "summary": "A backend role."}
    return JobAnalysis.parse(**(base | fields))


def message(**fields: Any) -> str:
    with pytest.raises(InvalidValue) as error:
        parse(**fields)
    return error.value.message


# --- розбір ---------------------------------------------------------------------


def test_a_minimal_analysis_has_empty_optional_parts() -> None:
    analysis = parse()
    assert analysis == JobAnalysis(score=70, summary="A backend role.")
    assert (analysis.seniority, analysis.work_mode, analysis.relocation) == (
        None,
        None,
        None,
    )


def test_every_field_is_kept() -> None:
    analysis = parse(
        must_have=["Python"],
        nice_to_have=["Go"],
        keywords=["asyncio"],
        seniority="senior",
        work_mode="remote",
        location="Madrid",
        languages=["English"],
        salary_min_eur=60000,
        salary_max_eur=80000,
        relocation=True,
        reasons=["Fits"],
        gaps=["No Go"],
    )
    assert (analysis.must_have, analysis.nice_to_have, analysis.keywords) == (
        ("Python",),
        ("Go",),
        ("asyncio",),
    )
    assert (analysis.seniority, analysis.work_mode) == (
        Seniority.SENIOR,
        WorkMode.REMOTE,
    )
    assert (analysis.location, analysis.languages) == ("Madrid", ("English",))
    assert (analysis.salary_min_eur, analysis.salary_max_eur) == (60000, 80000)
    assert (analysis.relocation, analysis.reasons, analysis.gaps) == (
        True,
        ("Fits",),
        (Gap("No Go"),),
    )


def test_the_summary_and_location_are_collapsed_to_one_line() -> None:
    analysis = parse(summary="  A  backend\n role. ", location=" Madrid ,\n Spain ")
    assert (analysis.summary, analysis.location) == (
        "A backend role.",
        "Madrid , Spain",
    )


def test_a_blank_location_is_not_stated() -> None:
    assert parse(location="  \n ").location is None


def test_items_lose_spaces_empties_and_case_insensitive_repeats() -> None:
    analysis = parse(must_have=["  Python ", "", "python", "Go\n lang", "  "])
    assert analysis.must_have == ("Python", "Go lang")


def test_enums_are_read_without_case_and_spaces() -> None:
    analysis = parse(seniority=" Senior ", work_mode="HYBRID")
    assert (analysis.seniority, analysis.work_mode) == (
        Seniority.SENIOR,
        WorkMode.HYBRID,
    )


def test_an_unknown_seniority_lists_the_allowed_values() -> None:
    assert message(seniority="guru") == (
        "seniority: 'guru' — допустимо junior, middle, senior, lead, principal або порожньо."
    )


def test_an_unknown_work_mode_lists_the_allowed_values() -> None:
    assert message(work_mode="office") == (
        "work_mode: 'office' — допустимо remote, hybrid, onsite або порожньо."
    )


# --- ліміти ---------------------------------------------------------------------


@pytest.mark.parametrize("score", [0, 100])
def test_the_score_bounds_are_valid(score: int) -> None:
    assert parse(score=score).score == score


@pytest.mark.parametrize("score", [-1, 101])
def test_a_score_outside_0_to_100_is_rejected(score: int) -> None:
    assert message(score=score) == "Скор — ціле число від 0 до 100."


@pytest.mark.parametrize("summary", ["", "   \n"])
def test_an_empty_summary_is_rejected(summary: str) -> None:
    assert message(summary=summary) == "summary — від 1 до 1000 символів."


def test_a_summary_of_1000_characters_is_valid_and_1001_is_not() -> None:
    assert len(parse(summary="x" * 1000).summary) == 1000
    assert message(summary="x" * 1001) == "summary — від 1 до 1000 символів."


def test_a_location_over_200_characters_is_rejected() -> None:
    assert len(parse(location="x" * 200).location or "") == 200
    assert message(location="x" * 201) == "location — до 200 символів."


@pytest.mark.parametrize("name", ["must_have", "nice_to_have", "languages", "reasons"])
def test_30_items_are_valid_and_31_are_not(name: str) -> None:
    ok = [f"item {n}" for n in range(30)]
    assert len(getattr(parse(**{name: ok}), name)) == 30
    assert message(**{name: [*ok, "one more"]}) == f"{name} — не більше 30 пунктів."


@pytest.mark.parametrize("name", ["must_have", "nice_to_have", "languages", "reasons"])
def test_an_item_over_300_characters_is_rejected(name: str) -> None:
    assert len(getattr(parse(**{name: ["x" * 300]}), name)[0]) == 300
    assert message(**{name: ["x" * 301]}) == (
        f"{name}: кожен пункт — від 1 до 300 символів."
    )


def test_30_gaps_are_valid_and_31_are_not() -> None:
    ok = [f"gap {n}" for n in range(30)]
    assert len(parse(gaps=ok).gaps) == 30
    assert message(gaps=[*ok, "one more"]) == "gaps — не більше 30 пунктів."


def test_a_gap_text_over_300_characters_is_rejected() -> None:
    assert len(parse(gaps=["x" * 300]).gaps[0].gap) == 300
    assert message(gaps=["x" * 301]) == "gaps: кожен пункт — від 1 до 300 символів."


# --- прогалини з питаннями -----------------------------------------------------------

QUESTION = "Чи працювали з Kubernetes? Де, скільки, що саме?"


def test_a_gap_object_keeps_its_text_and_question() -> None:
    analysis = parse(gaps=[Gap("Kubernetes", QUESTION), Gap("Go", "Чи писали на Go?")])
    assert analysis.gaps == (
        Gap("Kubernetes", QUESTION),
        Gap("Go", "Чи писали на Go?"),
    )


def test_a_plain_string_gap_is_the_old_format_with_no_question() -> None:
    assert parse(gaps=["Kubernetes"]).gaps == (Gap("Kubernetes", None),)


def test_strings_and_objects_may_be_mixed() -> None:
    analysis = parse(gaps=["Go", Gap("Kubernetes", QUESTION)])
    assert analysis.gaps == (Gap("Go", None), Gap("Kubernetes", QUESTION))


def test_no_gaps_is_valid() -> None:
    assert parse(gaps=[]).gaps == ()
    assert parse().gaps == ()


def test_gap_text_and_question_lose_extra_spaces_and_line_breaks() -> None:
    analysis = parse(gaps=[Gap("  Kuber\n netes ", "  Чи   був\nдосвід? ")])
    assert analysis.gaps == (Gap("Kuber netes", "Чи був досвід?"),)


def test_a_repeated_gap_text_is_kept_once_ignoring_case() -> None:
    analysis = parse(gaps=[Gap("Go", "Q1?"), Gap(" go ", "Q2?"), "GO"])
    assert analysis.gaps == (Gap("Go", "Q1?"),)


@pytest.mark.parametrize("question", [None, "", "  \n "])
def test_a_gap_object_without_a_question_is_rejected_with_its_number(
    question: str | None,
) -> None:
    assert message(gaps=[Gap("Kubernetes", question)]) == (
        "gaps: у прогалини 1 нема питання."
    )


def test_the_number_in_the_refusal_is_the_place_in_the_sent_list() -> None:
    assert message(
        gaps=["Go", Gap("Rust", "Чи писали на Rust?"), Gap("Kubernetes", None)]
    ) == ("gaps: у прогалини 3 нема питання.")


def test_a_gap_object_without_text_is_rejected_with_its_number() -> None:
    assert message(gaps=[Gap("Go", "Q?"), Gap(" ", "Q?")]) == (
        "gaps: у прогалини 2 нема тексту."
    )


def test_a_question_of_300_characters_is_valid_and_301_is_not() -> None:
    assert len(parse(gaps=[Gap("Go", "q" * 300)]).gaps[0].question or "") == 300
    assert message(gaps=[Gap("Go", "Q?"), Gap("Rust", "q" * 301)]) == (
        "gaps: питання прогалини 2 довше за 300 символів."
    )


def test_60_keywords_of_80_characters_are_valid_and_more_are_not() -> None:
    assert len(parse(keywords=[f"{n:02}" + "x" * 78 for n in range(60)]).keywords) == 60
    assert message(keywords=[f"k{n}" for n in range(61)]) == (
        "keywords — не більше 60 пунктів."
    )
    assert message(keywords=["x" * 81]) == (
        "keywords: кожен пункт — від 1 до 80 символів."
    )


def test_keywords_without_a_bar_are_kept_as_single_spelling_requirements() -> None:
    keywords = ["asyncio", "C#", "payment latency", "Node.js"]

    assert parse(keywords=keywords).keywords == tuple(keywords)


def test_a_keyword_group_is_kept_with_one_space_around_each_bar() -> None:
    assert parse(keywords=["Java|TypeScript  |  Python"]).keywords == (
        "Java | TypeScript | Python",
    )


def test_a_keyword_group_of_5_spellings_is_valid_and_6_are_not() -> None:
    assert parse(keywords=["a | b | c | d | e"]).keywords == ("a | b | c | d | e",)
    assert message(keywords=["a | b | c | d | e | f"]) == (
        "keywords: «a | b | c | d | e | f» — не більше 5 варіантів через «|»."
    )


@pytest.mark.parametrize(
    ("keyword", "shown"),
    [
        ("Java | ", "Java |"),
        ("| Java", "| Java"),
        ("Java |  | Python", "Java | | Python"),
        ("|", "|"),
    ],
)
def test_a_keyword_group_with_an_empty_spelling_is_rejected(
    keyword: str, shown: str
) -> None:
    assert message(keywords=[keyword]) == (
        f"keywords: у «{shown}» є порожній варіант між «|»."
    )


# --- карта «ключове слово → факти» ----------------------------------------------


def test_an_analysis_without_the_map_has_none_and_an_empty_map_is_not_none() -> None:
    assert parse(keywords=["Python"]).keyword_facts is None
    assert parse(keywords=["Python"], keyword_facts={}).keyword_facts == ()


def test_the_map_keeps_the_keyword_as_written_in_the_list_of_keywords() -> None:
    analysis = parse(
        keywords=["Java | Python", "Kafka"],
        keyword_facts={"python|JAVA ": [4], "kafka": [2, 7]},
    )

    assert analysis.keyword_facts == (
        KeywordFacts("Java | Python", (4,)),
        KeywordFacts("Kafka", (2, 7)),
    )


def test_fact_numbers_in_the_map_have_no_repeats() -> None:
    analysis = parse(keywords=["Kafka"], keyword_facts={"Kafka": [3, 1, 3]})

    assert analysis.keyword_facts == (KeywordFacts("Kafka", (3, 1)),)


def test_a_map_key_that_is_not_a_keyword_is_rejected() -> None:
    assert message(keywords=["Kafka"], keyword_facts={"Rust": [1]}) == (
        "keyword_facts: «Rust» — такого ключового слова нема в keywords."
    )


def test_the_constructor_refuses_a_keyword_group_with_an_empty_spelling() -> None:
    with pytest.raises(InvalidValue) as error:
        JobAnalysis(score=1, summary="s", keywords=("Java | ",))
    assert error.value.message == "keywords: у «Java | » є порожній варіант між «|»."


def test_the_constructor_still_refuses_an_empty_item() -> None:
    with pytest.raises(InvalidValue) as error:
        JobAnalysis(score=1, summary="s", must_have=("",))
    assert error.value.message == "must_have: кожен пункт — від 1 до 300 символів."


@pytest.mark.parametrize("name", ["salary_min_eur", "salary_max_eur"])
def test_a_salary_outside_0_to_10_million_is_rejected(name: str) -> None:
    assert getattr(parse(**{name: 0}), name) == 0
    assert getattr(parse(**{name: 10_000_000}), name) == 10_000_000
    expected = f"{name} — від 0 до 10000000 EUR на рік."
    assert message(**{name: -1}) == expected
    assert message(**{name: 10_000_001}) == expected


def test_a_minimum_above_the_maximum_is_rejected() -> None:
    assert message(salary_min_eur=90000, salary_max_eur=80000) == (
        "salary_min_eur більша за salary_max_eur."
    )
    assert parse(salary_min_eur=80000, salary_max_eur=80000).salary_ceiling == 80000


def test_the_salary_ceiling_is_the_top_of_the_range_else_the_bottom() -> None:
    assert parse(salary_min_eur=50000, salary_max_eur=70000).salary_ceiling == 70000
    assert parse(salary_min_eur=50000).salary_ceiling == 50000
    assert parse(salary_max_eur=70000).salary_ceiling == 70000
    assert parse().salary_ceiling is None


# --- фільтри профілю --------------------------------------------------------------


def profile(
    work_modes: frozenset[WorkMode] = frozenset(),
    seniority: frozenset[Seniority] = frozenset(),
    min_salary: int | None = None,
    stop_words: tuple[str, ...] = (),
) -> Profile:
    return Profile(
        target=Target(seniority=seniority, min_salary_eur=min_salary),
        locations=Locations(work_modes=work_modes),
        rules=Rules(stop_words=stop_words),
    )


POSTING = "Backend Engineer\nAcme\nWe build payments. Onsite culture, crypto friendly."


def test_a_job_that_fits_gets_no_flags() -> None:
    mine = profile(
        frozenset({WorkMode.REMOTE}),
        frozenset({Seniority.SENIOR}),
        60000,
        ("gambling",),
    )
    analysis = parse(work_mode="remote", seniority="senior", salary_max_eur=80000)
    assert apply_filters(analysis, mine, POSTING) == ()


def test_a_work_mode_outside_the_profile_is_flagged() -> None:
    flags = apply_filters(
        parse(work_mode="onsite"), profile(frozenset({WorkMode.REMOTE})), POSTING
    )
    assert flags == ("Формат onsite — не з профілю.",)


def test_a_seniority_outside_the_profile_is_flagged() -> None:
    flags = apply_filters(
        parse(seniority="junior"),
        profile(seniority=frozenset({Seniority.SENIOR, Seniority.LEAD})),
        POSTING,
    )
    assert flags == ("Рівень junior — не з профілю.",)


def test_a_salary_ceiling_below_the_minimum_is_flagged() -> None:
    flags = apply_filters(
        parse(salary_min_eur=40000, salary_max_eur=55000),
        profile(min_salary=60000),
        POSTING,
    )
    assert flags == ("ЗП до 55000 EUR — менше мінімуму 60000 EUR.",)


def test_a_range_reaching_the_minimum_passes_by_its_top() -> None:
    analysis = parse(salary_min_eur=40000, salary_max_eur=65000)
    assert apply_filters(analysis, profile(min_salary=60000), POSTING) == ()


def test_a_lone_minimum_counts_as_the_ceiling() -> None:
    flags = apply_filters(
        parse(salary_min_eur=30000), profile(min_salary=60000), POSTING
    )
    assert flags == ("ЗП до 30000 EUR — менше мінімуму 60000 EUR.",)


def test_a_stop_word_in_the_posting_is_flagged_without_case() -> None:
    flags = apply_filters(parse(), profile(stop_words=("CRYPTO",)), POSTING)
    assert flags == ("Стоп-слово: CRYPTO.",)


def test_each_stop_word_gets_its_own_flag_in_profile_order() -> None:
    flags = apply_filters(
        parse(), profile(stop_words=("payments", "gambling", "onsite")), POSTING
    )
    assert flags == ("Стоп-слово: payments.", "Стоп-слово: onsite.")


def test_all_filters_flag_in_the_order_mode_level_salary_stop_words() -> None:
    mine = profile(
        frozenset({WorkMode.REMOTE}),
        frozenset({Seniority.SENIOR}),
        90000,
        ("crypto",),
    )
    analysis = parse(work_mode="onsite", seniority="junior", salary_max_eur=50000)
    assert apply_filters(analysis, mine, POSTING) == (
        "Формат onsite — не з профілю.",
        "Рівень junior — не з профілю.",
        "ЗП до 50000 EUR — менше мінімуму 90000 EUR.",
        "Стоп-слово: crypto.",
    )


def test_what_the_job_does_not_state_never_fails_a_filter() -> None:
    mine = profile(frozenset({WorkMode.REMOTE}), frozenset({Seniority.SENIOR}), 90000)
    assert apply_filters(parse(), mine, POSTING) == ()


def test_what_the_profile_does_not_state_never_fails_a_filter() -> None:
    analysis = parse(work_mode="onsite", seniority="junior", salary_max_eur=1000)
    assert apply_filters(analysis, Profile(), POSTING) == ()


# --- значення рубрики -------------------------------------------------------------


def test_the_rubric_names_the_candidate_and_gives_domain_examples() -> None:
    mine = Profile(
        target=Target(target_domains=("fintech", "payments")),
        contacts=Contacts(full_name="Test User"),
    )
    values = rubric_values(mine)
    assert (values.candidate, values.domain_examples) == (
        "Test User",
        " (e.g. fintech, payments)",
    )


def test_an_empty_profile_gives_a_neutral_candidate_and_no_examples() -> None:
    values = rubric_values(Profile())
    assert (values.candidate, values.domain_examples) == (NEUTRAL_CANDIDATE, "")
    assert NEUTRAL_CANDIDATE == "the candidate"


# --- що в профілі впливає на аналіз -------------------------------------------------


def test_a_changed_target_locations_or_rules_change_the_analysis_inputs() -> None:
    base = Profile()
    assert base.changes_analysis_inputs(Profile(target=Target(roles=("QA",))))
    assert base.changes_analysis_inputs(Profile(locations=Locations(relocation=True)))
    assert base.changes_analysis_inputs(Profile(rules=Rules(stop_words=("x",))))


def test_contacts_and_identical_sections_do_not() -> None:
    base = Profile(target=Target(roles=("QA",)))
    assert not base.changes_analysis_inputs(base)
    assert not base.changes_analysis_inputs(
        Profile(
            target=Target(roles=("QA",)),
            contacts=Contacts(full_name="Test User", email="a@b.co"),
        )
    )
