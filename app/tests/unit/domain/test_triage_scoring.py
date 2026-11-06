"""Тріаж без LLM: скор за рубрикою аналізу (40 / 20 / 15 / 10 / 10 / 5), вердикт, причина, відбиток."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from domain.analysis.analysis import JobAnalysis, apply_filters
from domain.jobs.ids import JobId
from domain.jobs.job import Job
from domain.profile.contacts import Contacts
from domain.profile.locations import Locations, SearchLocation
from domain.profile.modes import Seniority, WorkMode
from domain.profile.profile import Profile
from domain.profile.rules import Rules
from domain.profile.target import Target
from domain.sources.filtering import infer_mode
from domain.triage import scoring
from domain.triage.scoring import (
    RULES_VERSION,
    AutoTriage,
    Breakdown,
    Mismatch,
    auto_triage,
    context_digest,
    inputs_hash,
    offered_modes,
    verdict_for,
)
from domain.triage.triage import MAX_REASON_LENGTH, TriageVerdict

NOW = datetime(2026, 11, 4, 8, 0, tzinfo=UTC)
FULL_FIT_TEXT = """We build payments for fintech.
Requirements:
- Python
- PostgreSQL
- Docker
Nice to have:
- Kafka
Compensation: €70k-90k per year
"""
FACTS = [
    "Python for 5 years",
    "Operated PostgreSQL clusters",
    "Docker in production",
    "Kafka streaming pipelines",
]
# Рівно 8 обов'язкових вимог: кожен підкріплений факт дає 5 балів із 40.
EIGHT = "Requirements:\nPython, Java, Kotlin, Rust, Scala, Elixir, PHP, Ruby"
EIGHT_FACTS = ["Python", "Java", "Kotlin", "Rust", "Scala", "Elixir", "PHP", "Ruby"]


def job(
    title: str | None = "Engineer",
    text: str = "Great job.",
    location: str | None = None,
) -> Job:
    return Job(
        id=JobId(UUID(int=1)),
        number=1,
        source="manual",
        text=text,
        url=None,
        title=title,
        company="Acme",
        created_at=NOW,
        location=location,
    )


def profile(
    *,
    target: Target | None = None,
    locations: Locations | None = None,
    rules: Rules | None = None,
) -> Profile:
    return Profile(
        target=target or Target(),
        locations=locations or Locations(),
        rules=rules or Rules(),
    )


FULL_PROFILE = profile(
    target=Target(
        roles=("Backend Engineer",),
        seniority=frozenset({Seniority.SENIOR}),
        min_salary_eur=60_000,
        target_domains=("fintech", "payments"),
    ),
    locations=Locations(
        work_modes=frozenset({WorkMode.REMOTE, WorkMode.HYBRID}),
        locations=(
            SearchLocation(
                "Valencia", ("Валенсія",), frozenset({WorkMode.REMOTE, WorkMode.HYBRID})
            ),
        ),
    ),
    rules=Rules(stop_words=("blockchain",)),
)
FULL_FIT = job("Senior Backend Engineer", FULL_FIT_TEXT, "Valencia, Spain (Remote)")


def triage(
    posting: Job, prof: Profile | None = None, facts: list[str] | None = None
) -> AutoTriage:
    return auto_triage(posting, prof or profile(), facts or [])


def test_a_job_that_fits_everything_scores_100_and_is_analysed() -> None:
    assert triage(FULL_FIT, FULL_PROFILE, FACTS) == AutoTriage(
        100, TriageVerdict.ANALYSE, "Підходить: підкріплено 3 з 3 обов'язкових вимог."
    )


def test_a_job_with_no_evidence_gets_the_unrestricted_baseline_of_50() -> None:
    # 20 нейтральна половина вимог + 12 роль + 8 рівень + 8 невідомий формат + 2 зарплата не вказана.
    assert triage(job()) == AutoTriage(
        50, TriageVerdict.MAYBE, "Невпевнено: у тексті мало вимог (розпізнано 0)."
    )


def test_must_haves_score_in_proportion_to_the_facts_that_back_them() -> None:
    result = triage(job(text="Requirements:\n- Python\n- Kafka"), facts=["Python"])
    assert result == AutoTriage(
        50,
        TriageVerdict.MAYBE,
        "Невпевнено: у тексті мало вимог (розпізнано 2);"
        " підкріплено 1 з 2 обов'язкових вимог; бракує Kafka.",
    )


def test_the_must_have_share_is_rounded_to_a_whole_point() -> None:
    posting = job(text="Requirements:\n- Python\n- Kafka\n- Redis")
    assert triage(posting, facts=["Python"]).score == 43


def test_nice_to_haves_score_in_proportion_to_the_facts_that_back_them() -> None:
    posting = job(text="Requirements:\nPython\nNice to have:\nKafka\nRedis")
    assert triage(posting, facts=["Python", "Kafka"]).score == 75


def test_two_recognised_requirements_are_too_few_to_advise_analysis() -> None:
    posting = job(text="Requirements:\nPython\nDocker")
    assert triage(posting, facts=["Python", "Docker"]) == AutoTriage(
        70,
        TriageVerdict.MAYBE,
        "Невпевнено: у тексті мало вимог (розпізнано 2);"
        " підкріплено 2 з 2 обов'язкових вимог.",
    )


def test_three_recognised_requirements_with_a_score_of_55_are_analysed() -> None:
    posting = job(text=EIGHT)
    result = triage(posting, facts=EIGHT_FACTS[:5])
    assert (result.score, result.verdict) == (55, TriageVerdict.ANALYSE)


def test_a_score_of_50_is_only_maybe() -> None:
    posting = job(text=EIGHT)
    result = triage(posting, facts=EIGHT_FACTS[:4])
    assert (result.score, result.verdict) == (50, TriageVerdict.MAYBE)


def test_a_score_of_40_is_maybe_and_lists_what_the_facts_do_not_back() -> None:
    posting = job(text="Requirements:\nPython, Java, Kotlin, Rust")
    assert triage(posting, facts=["Python"]) == AutoTriage(
        40,
        TriageVerdict.MAYBE,
        "Невпевнено: підкріплено 1 з 4 обов'язкових вимог; бракує Java, Kotlin, Rust.",
    )


def test_a_score_of_38_is_skip_without_a_mismatch() -> None:
    posting = job(text="Requirements:\nPython, Java, Kotlin, Rust, Scala")
    assert triage(posting, facts=["Python"]) == AutoTriage(
        38, TriageVerdict.SKIP, "Слабкий збіг: підкріплено 1 з 5 обов'язкових вимог."
    )


@pytest.mark.parametrize(
    ("score", "verdict"),
    [
        (100, TriageVerdict.ANALYSE),
        (55, TriageVerdict.ANALYSE),
        (54, TriageVerdict.MAYBE),
        (40, TriageVerdict.MAYBE),
        (39, TriageVerdict.SKIP),
        (0, TriageVerdict.SKIP),
    ],
)
def test_a_bare_score_maps_to_a_verdict(score: int, verdict: TriageVerdict) -> None:
    assert verdict_for(score) is verdict


def test_a_title_matching_a_profile_role_scores_12_and_another_title_0() -> None:
    prof = profile(target=Target(roles=("Backend Engineer",)))
    assert triage(job("Senior Backend Engineer"), prof).score == 50
    assert triage(job("Frontend Developer"), prof).score == 38


def test_every_word_of_a_role_must_be_in_the_title() -> None:
    prof = profile(target=Target(roles=("Backend Engineer",)))
    assert triage(job("Backend Developer"), prof).score == 38
    assert triage(job("Engineer, Backend"), prof).score == 50


def test_a_level_from_the_profile_scores_8_and_an_unknown_level_4() -> None:
    prof = profile(
        target=Target(seniority=frozenset({Seniority.SENIOR, Seniority.LEAD}))
    )
    assert triage(job("Lead Engineer"), prof).score == 50
    assert triage(job("Engineer"), prof).score == 46
    assert triage(job(None), prof).score == 46


def test_a_level_outside_the_profile_is_a_mismatch_that_skips() -> None:
    prof = profile(target=Target(seniority=frozenset({Seniority.SENIOR})))
    assert triage(job("Junior Engineer"), prof) == AutoTriage(
        42, TriageVerdict.SKIP, "Не підходить: рівень."
    )


def test_a_known_format_the_profile_allows_scores_15() -> None:
    assert triage(job(text="Remote position.")).score == 57


def test_an_unknown_format_scores_8_when_the_profile_includes_unknown() -> None:
    assert (
        triage(job(), profile(locations=Locations(include_unknown_mode=True))).score
        == 50
    )


def test_an_unknown_format_scores_0_when_the_profile_excludes_unknown() -> None:
    prof = profile(locations=Locations(include_unknown_mode=False))
    assert triage(job(), prof).score == 42


def test_a_format_outside_the_profile_is_a_mismatch_that_skips() -> None:
    prof = profile(locations=Locations(work_modes=frozenset({WorkMode.REMOTE})))
    posting = job(text="Hybrid, three days in the office.", location="Berlin")
    assert triage(posting, prof) == AutoTriage(
        42, TriageVerdict.SKIP, "Не підходить: формат чи локація."
    )


def test_a_place_outside_the_profile_is_a_mismatch_that_skips() -> None:
    posting = job("Senior Backend Engineer", "Hybrid role.", "Berlin")
    assert triage(posting, FULL_PROFILE) == AutoTriage(
        42, TriageVerdict.SKIP, "Не підходить: формат чи локація."
    )


def test_a_place_synonym_from_the_profile_matches_the_location() -> None:
    posting = job("Senior Backend Engineer", "Remote role.", "Валенсія")
    assert triage(posting, FULL_PROFILE).score == 57


def test_each_target_domain_in_the_text_scores_5_up_to_10() -> None:
    prof = profile(target=Target(target_domains=("fintech", "payments")))
    assert triage(job(text="We are a fintech."), prof).score == 55
    assert triage(job(text="We build fintech payments."), prof).score == 60


def test_a_salary_at_or_above_the_minimum_scores_5_and_unstated_2() -> None:
    prof = profile(target=Target(min_salary_eur=60_000))
    assert triage(job(text="We pay €70k-90k."), prof).score == 53
    assert triage(job(text="We pay €50k-80k."), prof).score == 53
    assert triage(job(), prof).score == 50


def test_a_stated_salary_scores_5_when_the_profile_has_no_minimum() -> None:
    assert triage(job(text="We pay €40k.")).score == 53


def test_a_salary_below_the_minimum_is_a_mismatch_that_skips() -> None:
    prof = profile(target=Target(min_salary_eur=60_000))
    assert triage(job(text="We pay €40k-50k."), prof) == AutoTriage(
        48, TriageVerdict.SKIP, "Не підходить: зарплата нижче мінімуму."
    )


@pytest.mark.parametrize(
    ("title", "text"),
    [("Engineer", "Join our Blockchain team."), ("Blockchain Engineer", "Great job.")],
)
def test_a_stop_word_in_the_title_or_text_is_a_mismatch_that_skips(
    title: str, text: str
) -> None:
    prof = profile(rules=Rules(stop_words=("blockchain",)))
    assert triage(job(title, text), prof) == AutoTriage(
        50, TriageVerdict.SKIP, "Не підходить: стоп-слово."
    )


def test_a_mismatch_skips_even_when_the_score_is_high() -> None:
    posting = replace(FULL_FIT, title="Junior Backend Engineer")
    result = triage(posting, FULL_PROFILE, FACTS)
    assert (result.score, result.verdict) == (92, TriageVerdict.SKIP)


def test_all_mismatches_are_listed_and_the_reason_fits_the_limit() -> None:
    prof = replace(
        FULL_PROFILE,
        target=replace(FULL_PROFILE.target, min_salary_eur=200_000),
    )
    posting = job(
        "Junior Engineer", "Hybrid blockchain job, pays €40k.", "Berlin (Hybrid)"
    )
    result = triage(posting, prof)
    assert result.reason == (
        "Не підходить: формат чи локація, рівень, зарплата нижче мінімуму, стоп-слово."
    )
    assert len(result.reason) <= MAX_REASON_LENGTH


def test_a_requirement_no_fact_backs_scores_nothing() -> None:
    posting = job(text="Requirements:\nPython")
    assert triage(posting, facts=["Java"]).score == 30


def test_a_term_is_backed_by_any_fact_that_mentions_it() -> None:
    posting = job(text="Requirements:\nPostgreSQL")
    assert triage(posting, facts=["Tuned Postgres queries"]).score == 70


def test_the_digest_is_a_sha256_hex_independent_of_fact_order() -> None:
    digest = context_digest(FULL_PROFILE, ["a", "b"])
    assert len(digest) == 64
    assert int(digest, 16) >= 0
    assert digest == context_digest(FULL_PROFILE, ["b", "a"])


@pytest.mark.parametrize(
    "changed",
    [
        replace(FULL_PROFILE, target=Target(roles=("Data Engineer",))),
        replace(FULL_PROFILE, locations=Locations(include_unknown_mode=False)),
        replace(FULL_PROFILE, rules=Rules(stop_words=("crypto",))),
    ],
)
def test_a_profile_change_changes_the_digest(changed: Profile) -> None:
    assert context_digest(changed, ["a"]) != context_digest(FULL_PROFILE, ["a"])


def test_a_new_confirmed_fact_changes_the_digest() -> None:
    assert context_digest(FULL_PROFILE, ["a", "b"]) != context_digest(
        FULL_PROFILE, ["a"]
    )


def test_contacts_do_not_change_the_digest() -> None:
    with_contacts = replace(FULL_PROFILE, contacts=Contacts(full_name="Taras"))
    assert context_digest(with_contacts, ["a"]) == context_digest(FULL_PROFILE, ["a"])


def test_the_digest_does_not_depend_on_the_order_of_set_members() -> None:
    one = profile(
        target=Target(seniority=frozenset({Seniority.SENIOR, Seniority.LEAD}))
    )
    other = profile(
        target=Target(seniority=frozenset({Seniority.LEAD, Seniority.SENIOR}))
    )
    assert context_digest(one, []) == context_digest(other, [])


def test_the_inputs_hash_changes_with_the_title_location_text_or_context() -> None:
    base = inputs_hash("ctx", job("T", "text", "Madrid"))
    assert len(base) == 64
    assert base == inputs_hash("ctx", job("T", "text", "Madrid"))
    assert base != inputs_hash("ctx", job("T2", "text", "Madrid"))
    assert base != inputs_hash("ctx", job("T", "text2", "Madrid"))
    assert base != inputs_hash("ctx", job("T", "text", "Valencia"))
    assert base != inputs_hash("ctx", job("T", "text", None))
    assert base != inputs_hash("other", job("T", "text", "Madrid"))


def test_the_rules_version_is_a_positive_whole_number() -> None:
    assert isinstance(RULES_VERSION, int)
    assert RULES_VERSION >= 1


def test_the_inputs_hash_changes_with_the_rules_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posting = job("T", "text", "Madrid")
    before = inputs_hash("ctx", posting)

    monkeypatch.setattr(scoring, "RULES_VERSION", RULES_VERSION + 1)

    after = inputs_hash("ctx", posting)
    assert len(after) == 64
    assert after != before
    monkeypatch.setattr(scoring, "RULES_VERSION", RULES_VERSION)
    assert inputs_hash("ctx", posting) == before


def test_the_context_digest_does_not_depend_on_the_rules_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = context_digest(FULL_PROFILE, FACTS)

    monkeypatch.setattr(scoring, "RULES_VERSION", RULES_VERSION + 1)

    assert context_digest(FULL_PROFILE, FACTS) == before


def test_the_inputs_hash_ignores_what_the_score_does_not_use() -> None:
    posting = job("T", "text", "Madrid")
    other = replace(posting, number=9, company="Other", url="https://x.example/1")
    assert inputs_hash("ctx", posting) == inputs_hash("ctx", other)


def test_a_title_word_the_profile_excludes_is_its_own_mismatch_that_skips() -> None:
    prof = profile(rules=Rules(title_exclude=("intern",)))
    assert triage(job("Intern Engineer"), prof) == AutoTriage(
        50, TriageVerdict.SKIP, "Не підходить: слово з виключень у назві."
    )


def test_a_title_without_the_profile_keywords_is_not_a_mismatch() -> None:
    prof = profile(rules=Rules(title_keywords=("python",)))
    assert triage(job("Engineer"), prof) == AutoTriage(
        50, TriageVerdict.MAYBE, "Невпевнено: у тексті мало вимог (розпізнано 0)."
    )


def points(result: AutoTriage) -> int:
    b = result.breakdown
    return b.must + b.role_level + b.format_location + b.domain + b.nice + b.salary


def test_the_breakdown_of_a_full_fit_gives_the_rubric_maximum_per_component() -> None:
    assert triage(FULL_FIT, FULL_PROFILE, FACTS).breakdown == Breakdown(
        must=40,
        role_level=20,
        format_location=15,
        domain=10,
        nice=10,
        salary=5,
        must_recognised=3,
        must_backed=3,
        nice_recognised=1,
        nice_backed=1,
        mismatches=(),
    )


def test_the_breakdown_of_a_bare_job_is_the_unrestricted_baseline() -> None:
    assert triage(job()).breakdown == Breakdown(
        must=20, role_level=20, format_location=8, salary=2
    )


def test_the_breakdown_counts_recognised_and_backed_requirements_separately() -> None:
    posting = job(
        text="Requirements:\n- Python\n- Kafka\n- Redis\nNice to have:\n- Docker"
    )
    b = triage(posting, facts=["Python", "Docker"]).breakdown
    assert (b.must, b.nice) == (13, 10)
    assert (b.must_recognised, b.must_backed) == (3, 1)
    assert (b.nice_recognised, b.nice_backed) == (1, 1)


def test_the_breakdown_names_the_fired_mismatches() -> None:
    prof = profile(
        target=Target(seniority=frozenset({Seniority.SENIOR})),
        rules=Rules(stop_words=("blockchain",)),
    )
    result = triage(job("Junior Engineer", "We do blockchain."), prof)
    assert result.breakdown.mismatches == (Mismatch.LEVEL, Mismatch.STOP_WORD)
    assert result.breakdown.role_level == 12


PROFILES_AND_POSTINGS = [
    pytest.param(FULL_FIT, FULL_PROFILE, FACTS, id="full-fit"),
    pytest.param(job(), profile(), [], id="bare"),
    pytest.param(
        job(text="Requirements:\n- Python\n- Kafka\n- Redis"),
        profile(),
        ["Python"],
        id="partial-must-rounded",
    ),
    pytest.param(
        job("Junior Engineer"),
        profile(target=Target(seniority=frozenset({Seniority.SENIOR}))),
        [],
        id="level-mismatch",
    ),
    pytest.param(
        job("Senior Backend Engineer", "We pay €30k-40k. Remote position."),
        FULL_PROFILE,
        [],
        id="salary-below-minimum",
    ),
    pytest.param(
        job("Chef", "Requirements:\nPython\nNice to have:\nKafka\nRemote."),
        FULL_PROFILE,
        FACTS,
        id="wrong-role",
    ),
    pytest.param(job(text=EIGHT), profile(), EIGHT_FACTS[:3], id="three-of-eight"),
    pytest.param(job("Python Developer"), profile(), [], id="no-requirements"),
    pytest.param(
        job("Software Engineer", "Requirements:\nPython\nJava"),
        profile(
            target=Target(roles=("Backend Engineer",)),
            rules=Rules(title_keywords=("software engineer",)),
        ),
        ["Python"],
        id="keyword-role-two-requirements",
    ),
]


@pytest.mark.parametrize(("posting", "prof", "facts"), PROFILES_AND_POSTINGS)
def test_the_breakdown_points_sum_to_the_score(
    posting: Job, prof: Profile, facts: list[str]
) -> None:
    result = triage(posting, prof, facts)
    assert points(result) == result.score
    assert result.score > 0


# Калібрування (K-S): мало вимог у тексті, роль за ключовими словами, домени в різних формах.
NO_UNKNOWN_MODE = profile(locations=Locations(include_unknown_mode=False))


def test_prose_requirements_without_dictionary_terms_get_half_of_the_must_points() -> (
    None
):
    posting = job(
        text="Minimum requirements:\nStrong ownership and clear communication."
    )
    result = triage(posting)
    assert (result.breakdown.must, result.breakdown.must_recognised) == (20, 0)
    assert result.score == 50


def test_a_recognised_must_requirement_no_fact_backs_still_scores_nothing() -> None:
    result = triage(job(text="Requirements:\nPython\nJava\nKotlin"), facts=["Rust"])
    assert result.breakdown.must == 0
    assert result.score == 30


def test_two_requirements_never_skip_by_score_alone() -> None:
    posting = job(text="Requirements:\nPython\nJava")
    assert triage(posting, NO_UNKNOWN_MODE) == AutoTriage(
        22,
        TriageVerdict.MAYBE,
        "Невпевнено: у тексті мало вимог (розпізнано 2);"
        " підкріплено 0 з 2 обов'язкових вимог; бракує Python, Java.",
    )


def test_only_nice_requirements_are_too_few_to_skip_and_the_must_gets_the_half() -> (
    None
):
    prof = profile(
        target=Target(roles=("Backend Engineer",)),
        locations=Locations(include_unknown_mode=False),
    )
    posting = job("Chef", "Nice to have:\nKafka")
    assert triage(posting, prof) == AutoTriage(
        30, TriageVerdict.MAYBE, "Невпевнено: у тексті мало вимог (розпізнано 1)."
    )


def test_three_requirements_with_a_low_score_are_still_skipped() -> None:
    posting = job(text="Requirements:\nPython\nJava\nKotlin")
    assert triage(posting, NO_UNKNOWN_MODE) == AutoTriage(
        22, TriageVerdict.SKIP, "Слабкий збіг: підкріплено 0 з 3 обов'язкових вимог."
    )


MISMATCHES = [
    pytest.param(
        job("Junior Engineer"),
        profile(target=Target(seniority=frozenset({Seniority.SENIOR}))),
        "рівень",
        id="level",
    ),
    pytest.param(
        job(text="Hybrid, three days in the office.", location="Berlin"),
        profile(locations=Locations(work_modes=frozenset({WorkMode.REMOTE}))),
        "формат чи локація",
        id="format",
    ),
    pytest.param(
        job(text="We pay €40k-50k."),
        profile(target=Target(min_salary_eur=60_000)),
        "зарплата нижче мінімуму",
        id="salary",
    ),
    pytest.param(
        job(text="Join our Blockchain team."),
        profile(rules=Rules(stop_words=("blockchain",))),
        "стоп-слово",
        id="stop-word",
    ),
]


@pytest.mark.parametrize(("posting", "prof", "mismatch"), MISMATCHES)
def test_a_hard_mismatch_skips_with_no_requirements_in_the_text(
    posting: Job, prof: Profile, mismatch: str
) -> None:
    result = triage(posting, prof)
    assert (result.verdict, result.reason) == (
        TriageVerdict.SKIP,
        f"Не підходить: {mismatch}.",
    )
    assert result.score >= 40


@pytest.mark.parametrize(("posting", "prof", "mismatch"), MISMATCHES)
def test_a_hard_mismatch_skips_with_one_nice_requirement_in_the_text(
    posting: Job, prof: Profile, mismatch: str
) -> None:
    text = f"{posting.text}\nNice to have:\nKafka"
    result = triage(replace(posting, text=text), prof)
    assert (result.verdict, result.reason) == (
        TriageVerdict.SKIP,
        f"Не підходить: {mismatch}.",
    )


KEYWORD_PROFILE = profile(
    target=Target(roles=("Backend Engineer",)),
    rules=Rules(
        title_keywords=("software engineer", "python", "backend", "AI"),
        title_exclude=("intern",),
    ),
)


@pytest.mark.parametrize(
    "title", ["Software Engineer, Flights", "Agentic AI Engineer", "Python Developer"]
)
def test_a_title_with_a_profile_keyword_but_no_role_scores_8_of_12(title: str) -> None:
    # 8 за ключове слово + 8 за рівень (профіль без рівнів).
    assert triage(job(title), KEYWORD_PROFILE).breakdown.role_level == 16


def test_a_title_without_a_role_or_a_keyword_scores_no_role_points() -> None:
    assert triage(job("Chef"), KEYWORD_PROFILE).breakdown.role_level == 8


def test_a_full_role_match_still_scores_12_even_with_a_keyword_in_the_title() -> None:
    result = triage(job("Senior Backend Engineer"), KEYWORD_PROFILE)
    assert result.breakdown.role_level == 20


def test_a_keyword_scores_nothing_when_the_title_has_an_excluded_word() -> None:
    result = triage(job("Python Intern"), KEYWORD_PROFILE)
    assert result.breakdown.role_level == 8
    assert result.breakdown.mismatches == (Mismatch.EXCLUDED_WORD,)


def test_keywords_do_not_match_inside_longer_words() -> None:
    assert triage(job("Mountain Chef"), KEYWORD_PROFILE).breakdown.role_level == 8


def test_domains_match_plurals_and_stems_in_the_posting() -> None:
    prof = profile(target=Target(target_domains=("fintech", "banking")))
    posting = job(text="Bank infrastructure for fintechs.")
    assert triage(posting, prof).breakdown.domain == 10


# Профіль з реальних даних: формат і локація за правилами аналізу (K-U).
REAL_PROFILE = profile(
    target=Target(roles=("Backend Engineer",)),
    locations=Locations(
        work_modes=frozenset({WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE}),
        locations=(
            SearchLocation("Spain", (), frozenset({WorkMode.REMOTE})),
            SearchLocation("Ukraine", (), frozenset({WorkMode.REMOTE})),
            SearchLocation(
                "Valencia",
                (),
                frozenset({WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE}),
            ),
            SearchLocation("Madrid", (), frozenset({WorkMode.HYBRID, WorkMode.ONSITE})),
            SearchLocation(
                "Barcelona", (), frozenset({WorkMode.HYBRID, WorkMode.ONSITE})
            ),
        ),
        include_unknown_mode=True,
    ),
)


def test_a_remote_posting_outside_the_profile_places_is_not_a_format_mismatch() -> None:
    posting = job("Backend Engineer", "Fully remote role.", "Portugal")
    result = triage(posting, REAL_PROFILE)
    assert result.breakdown.mismatches == ()
    assert result.breakdown.format_location == 15
    assert result.verdict is not TriageVerdict.SKIP


def test_an_onsite_posting_outside_the_profile_places_is_still_a_mismatch() -> None:
    posting = job("Backend Engineer", "Work from our office.", "Berlin")
    result = triage(posting, REAL_PROFILE)
    assert result.breakdown.mismatches == (Mismatch.FORMAT,)
    assert (result.verdict, result.reason) == (
        TriageVerdict.SKIP,
        "Не підходить: формат чи локація.",
    )


def test_a_hybrid_posting_outside_the_profile_places_is_still_a_mismatch() -> None:
    posting = job("Backend Engineer", "Hybrid, three days in the office.", "Berlin")
    assert triage(posting, REAL_PROFILE).breakdown.mismatches == (Mismatch.FORMAT,)


def test_a_posting_in_a_listed_place_with_an_allowed_mode_is_not_a_mismatch() -> None:
    posting = job("Backend Engineer", "Hybrid, two days in the office.", "Madrid")
    assert triage(posting, REAL_PROFILE).breakdown.mismatches == ()


REMOTE_HYBRID = frozenset({WorkMode.REMOTE, WorkMode.HYBRID})
REMOTE_ONLY = frozenset({WorkMode.REMOTE})


def agreement_profile(modes: frozenset[WorkMode]) -> Profile:
    place = SearchLocation("Valencia", (), modes)
    return profile(locations=Locations(work_modes=modes, locations=(place,)))


# (локація, текст, формати профілю, чи є невідповідність формату)
FORMAT_AGREEMENT = [
    pytest.param("Valencia", "Remote.", REMOTE_HYBRID, False, id="listed-remote"),
    pytest.param("Berlin", "Remote.", REMOTE_HYBRID, False, id="unlisted-remote"),
    pytest.param("Valencia", "Hybrid.", REMOTE_HYBRID, False, id="listed-hybrid"),
    pytest.param("Valencia", "Hybrid.", REMOTE_ONLY, True, id="hybrid-not-accepted"),
    pytest.param("Berlin", "Hybrid.", REMOTE_ONLY, True, id="unlisted-hybrid"),
    pytest.param(
        "Valencia", "Remote.", frozenset({WorkMode.HYBRID}), True, id="remote-refused"
    ),
    pytest.param("Valencia", "Great job.", REMOTE_HYBRID, False, id="mode-not-stated"),
    pytest.param(None, "Remote.", REMOTE_HYBRID, False, id="no-location-remote"),
    pytest.param(None, "Hybrid.", REMOTE_ONLY, True, id="no-location-hybrid-refused"),
    pytest.param(None, "Hybrid.", frozenset(), False, id="profile-without-modes"),
]


@pytest.mark.parametrize(("location", "text", "modes", "mismatch"), FORMAT_AGREEMENT)
def test_the_format_mismatch_agrees_with_the_analysis_hard_filters(
    location: str | None, text: str, modes: frozenset[WorkMode], mismatch: bool
) -> None:
    prof = agreement_profile(modes)
    analysis = JobAnalysis(
        score=50, summary="x", work_mode=infer_mode([location or "", text])
    )
    flagged = bool(apply_filters(analysis, prof, text))
    fired = (
        Mismatch.FORMAT
        in triage(job("Engineer", text, location), prof).breakdown.mismatches
    )
    assert flagged is mismatch
    assert fired is mismatch


REMOTE_FIRST = (
    "Remote-first company. Hybrid working option in Barcelona, Dublin and London."
)
BOTH_OPTIONS = "We offer both hybrid and fully remote working options."
BOTH = frozenset({WorkMode.REMOTE, WorkMode.HYBRID})


@pytest.mark.parametrize(
    ("texts", "modes"),
    [
        pytest.param(["", REMOTE_FIRST], BOTH, id="remote-first-with-hybrid-option"),
        pytest.param(["Dublin", BOTH_OPTIONS], BOTH, id="hybrid-or-fully-remote"),
        pytest.param(["Berlin", "Hybrid, 3 days."], {WorkMode.HYBRID}, id="hybrid"),
        pytest.param(["Remote - Spain", "Great job."], {WorkMode.REMOTE}, id="remote"),
        pytest.param(["Madrid", "Great job."], set(), id="nothing-stated"),
        pytest.param(
            ["", "Гібридний або віддалений формат."], BOTH, id="ukrainian-stems"
        ),
        pytest.param(["", "Гибрид или удалённо."], BOTH, id="russian-stems"),
        pytest.param([], set(), id="no-texts"),
    ],
)
def test_the_offered_modes_are_every_mode_the_posting_names(
    texts: list[str], modes: set[WorkMode]
) -> None:
    assert offered_modes(texts) == frozenset(modes)


def test_remote_first_with_a_hybrid_option_in_an_unlisted_city_is_not_a_mismatch() -> (
    None
):
    posting = job("Backend Engineer", REMOTE_FIRST, "Dublin")
    result = triage(posting, REAL_PROFILE)
    assert result.breakdown.mismatches == ()
    assert result.breakdown.format_location == 15
    assert result.verdict is not TriageVerdict.SKIP


def test_remote_first_with_a_hybrid_option_in_a_listed_city_is_not_a_mismatch() -> None:
    posting = job("Backend Engineer", REMOTE_FIRST, "Barcelona")
    assert triage(posting, REAL_PROFILE).breakdown.mismatches == ()


def test_hybrid_or_fully_remote_in_an_unlisted_city_is_not_a_mismatch() -> None:
    posting = job("Backend Engineer", BOTH_OPTIONS, "Dublin")
    result = triage(posting, REAL_PROFILE)
    assert result.breakdown.mismatches == ()
    assert result.breakdown.format_location == 15


def test_a_remote_option_passes_a_profile_that_accepts_remote_but_not_hybrid() -> None:
    posting = job("Engineer", BOTH_OPTIONS, "Valencia")
    result = triage(posting, agreement_profile(REMOTE_ONLY))
    assert result.breakdown.mismatches == ()


def test_a_hybrid_option_passes_a_profile_that_accepts_hybrid_but_not_remote() -> None:
    hybrid_only = agreement_profile(frozenset({WorkMode.HYBRID}))
    posting = job("Engineer", BOTH_OPTIONS, "Valencia")
    assert triage(posting, hybrid_only).breakdown.mismatches == ()


def test_a_hybrid_option_in_an_unlisted_city_does_not_help_a_profile_without_remote() -> (
    None
):
    hybrid_only = agreement_profile(frozenset({WorkMode.HYBRID}))
    posting = job("Engineer", BOTH_OPTIONS, "Berlin")
    assert triage(posting, hybrid_only).breakdown.mismatches == (Mismatch.FORMAT,)


def test_no_offered_mode_the_profile_accepts_is_a_format_mismatch() -> None:
    onsite_only = agreement_profile(frozenset({WorkMode.ONSITE}))
    posting = job("Engineer", BOTH_OPTIONS, "Valencia")
    assert triage(posting, onsite_only).breakdown.mismatches == (Mismatch.FORMAT,)


def test_a_posting_without_a_stated_mode_in_an_unlisted_city_is_still_a_mismatch() -> (
    None
):
    posting = job("Backend Engineer", "Work from our office.", "Berlin")
    assert triage(posting, REAL_PROFILE).breakdown.mismatches == (Mismatch.FORMAT,)


UNKNOWN_MODE_CASES = [
    # (include_unknown_mode, місце вакансії, чи є невідповідність, бали за формат)
    pytest.param(True, "Valencia", False, 8, id="unknown-allowed-listed-place"),
    pytest.param(False, "Valencia", True, 0, id="unknown-refused-listed-place"),
    pytest.param(True, "Berlin", True, 0, id="unknown-allowed-unlisted-place"),
    pytest.param(False, "Berlin", True, 0, id="unknown-refused-unlisted-place"),
]


@pytest.mark.parametrize(
    ("include_unknown", "location", "mismatch", "points"), UNKNOWN_MODE_CASES
)
def test_a_posting_without_a_stated_mode_follows_include_unknown_mode(
    include_unknown: bool, location: str, mismatch: bool, points: int
) -> None:
    prof = profile(
        locations=Locations(
            work_modes=REMOTE_HYBRID,
            locations=(SearchLocation("Valencia", (), REMOTE_HYBRID),),
            include_unknown_mode=include_unknown,
        )
    )
    result = triage(job("Engineer", "Great job.", location), prof)
    assert (Mismatch.FORMAT in result.breakdown.mismatches) is mismatch
    assert result.breakdown.format_location == points


FEED_PLACES = profile(
    locations=Locations(
        work_modes=REMOTE_HYBRID,
        locations=(SearchLocation("Valencia", (), REMOTE_HYBRID),),
        include_unknown_mode=True,
    )
)
FEED_PLACES_NO_UNKNOWN = replace(
    FEED_PLACES, locations=replace(FEED_PLACES.locations, include_unknown_mode=False)
)


def feed_job(text: str, location: str | None = None) -> Job:
    return replace(job("Backend Engineer", text, location), source="rss:dou")


def test_a_feed_job_without_location_or_format_is_an_unknown_format_not_a_mismatch() -> (
    None
):
    result = triage(feed_job("Great job."), FEED_PLACES)
    assert Mismatch.FORMAT not in result.breakdown.mismatches
    assert result.breakdown.format_location == 8


def test_that_feed_job_stays_a_format_mismatch_when_unknown_formats_are_refused() -> (
    None
):
    result = triage(feed_job("Great job."), FEED_PLACES_NO_UNKNOWN)
    assert Mismatch.FORMAT in result.breakdown.mismatches


def test_a_feed_job_with_a_location_outside_the_profile_and_no_format_is_a_mismatch() -> (
    None
):
    result = triage(feed_job("Great job.", "Київ"), FEED_PLACES)
    assert Mismatch.FORMAT in result.breakdown.mismatches


def test_a_feed_job_without_location_that_says_hybrid_outside_the_places_is_a_mismatch() -> (
    None
):
    result = triage(feed_job("Hybrid role."), FEED_PLACES)
    assert Mismatch.FORMAT in result.breakdown.mismatches


def test_a_feed_job_without_location_naming_a_profile_place_is_not_a_mismatch() -> None:
    result = triage(feed_job("Our office is in Valencia."), FEED_PLACES)
    assert Mismatch.FORMAT not in result.breakdown.mismatches


def test_a_salary_range_whose_top_reaches_the_minimum_is_not_a_mismatch() -> None:
    prof = profile(target=Target(min_salary_eur=60_000))
    posting = job(text="Pay: between 45.600 EUR and 61.800 EUR a year.")
    assert Mismatch.SALARY not in triage(posting, prof).breakdown.mismatches


def test_an_excluded_title_word_is_its_own_mismatch_not_a_level_one() -> None:
    prof = profile(rules=Rules(title_exclude=("magento",)))
    result = triage(job("Magento Developer"), prof)
    assert result.breakdown.mismatches == (Mismatch.EXCLUDED_WORD,)
    assert result.reason == "Не підходить: слово з виключень у назві."
    assert "рівень" not in result.reason
    assert result.verdict is TriageVerdict.SKIP


def test_an_excluded_title_word_with_a_real_level_mismatch_lists_both() -> None:
    prof = profile(
        target=Target(seniority=frozenset({Seniority.SENIOR})),
        rules=Rules(title_exclude=("magento",)),
    )
    result = triage(job("Junior Magento Developer"), prof)
    assert result.reason == "Не підходить: рівень, слово з виключень у назві."


def test_an_excluded_title_word_does_not_remove_the_level_points() -> None:
    prof = profile(rules=Rules(title_exclude=("magento",)))
    assert triage(job("Magento Developer"), prof).breakdown.role_level == 20


def test_rules_version_2_makes_stored_rules_rows_stale() -> None:
    assert RULES_VERSION == 2
