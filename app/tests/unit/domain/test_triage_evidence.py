"""Докази для тріажу: терміни й секції вимог, зарплата в EUR, рівень із назви, домени."""

import pytest

from domain.profile.modes import Seniority
from domain.triage.evidence import (
    Confidence,
    SalaryRange,
    extract_requirements,
    find_domains,
    find_terms,
    parse_salary_eur,
    seniority_from_title,
    terms_in_facts,
)


def test_synonyms_give_one_term() -> None:
    result = extract_requirements("Requirements:\n- postgres\n- PostgreSQL")
    assert result.must == ("PostgreSQL",)


@pytest.mark.parametrize(
    ("synonym", "term"),
    [
        ("k8s", "Kubernetes"),
        ("Golang", "Go"),
        ("js", "JavaScript"),
        ("Node.js", "Node.js"),
    ],
)
def test_a_synonym_maps_to_its_canonical_term(synonym: str, term: str) -> None:
    assert find_terms(f"Experience with {synonym}") == (term,)


def test_a_term_in_the_nice_section_is_not_in_must() -> None:
    result = extract_requirements("Requirements:\nPython\nNice to have:\nKubernetes")
    assert (result.must, result.nice) == (("Python",), ("Kubernetes",))


def test_a_term_in_both_sections_counts_as_must() -> None:
    result = extract_requirements("Requirements:\nDocker\nNice to have:\nDocker, Redis")
    assert (result.must, result.nice) == (("Docker",), ("Redis",))


def test_text_without_headings_is_all_must_with_low_confidence() -> None:
    text = "We need Python and Docker.\nNice to know Redis."
    result = extract_requirements(text)
    assert set(result.must) == {"Python", "Docker", "Redis"}
    assert (result.nice, result.confidence, result.text) == ((), Confidence.LOW, text)


def test_only_unrelated_headings_do_not_count_as_requirement_sections() -> None:
    text = "About us\nWe use Python\nBenefits\nFree lunch"
    result = extract_requirements(text)
    assert (result.must, result.confidence, result.text) == (
        ("Python",),
        Confidence.LOW,
        text,
    )


def test_recognised_sections_give_high_confidence() -> None:
    result = extract_requirements("Requirements:\nPython")
    assert result.confidence is Confidence.HIGH


@pytest.mark.parametrize(
    ("must_heading", "nice_heading"),
    [
        ("Requirements", "Nice to have"),
        ("What we are looking for", "Nice to have"),
        ("Must-have", "Nice to have"),
        ("Вимоги", "Буде плюсом"),
        ("Требования", "Будет плюсом"),
        ("Requisitos", "Se valora"),
        ("## Requirements", "**Nice to have**"),
        ("Requirements:", "Nice to have:"),
    ],
)
def test_headings_split_must_and_nice(must_heading: str, nice_heading: str) -> None:
    text = f"{must_heading}\nPython\n{nice_heading}\nKubernetes"
    result = extract_requirements(text)
    assert (result.must, result.nice) == (("Python",), ("Kubernetes",))


@pytest.mark.parametrize(
    ("must_heading", "nice_heading"),
    [
        ("SOBRE TÍ", "DESEABLES / NICE TO HAVE"),
        ("Sobre ti:", "Se valorará:"),
        ("Lo que aportas", "También valoramos"),
        ("Minimum qualifications", "Good to have"),
        ("The ideal candidate", "Additional Experience That Would Be An Advantage"),
        ("Who you are", "Additional skills"),
        ("What you will bring", "Preferred qualifications"),
    ],
)
def test_calibrated_headings_split_must_and_nice(
    must_heading: str, nice_heading: str
) -> None:
    text = f"{must_heading}\nPython\n{nice_heading}\nKubernetes"
    result = extract_requirements(text)
    assert (result.must, result.nice) == (("Python",), ("Kubernetes",))


@pytest.mark.parametrize(
    "after",
    ["Accountabilities", "Key accountabilities:", "What you'll be doing", "Tu misión"],
)
def test_calibrated_other_headings_end_the_requirements(after: str) -> None:
    text = f"Requirements:\nPython\n{after}\nKubernetes budget"
    result = extract_requirements(text)
    assert (result.must, result.nice, result.text) == (("Python",), (), "Python")


def test_a_long_sentence_starting_like_a_new_heading_is_still_not_a_heading() -> None:
    line = "Additional experience with large regulated Kafka platforms is welcome"
    result = extract_requirements(f"Requirements:\n{line}")
    assert result.must == ("Kafka",)


@pytest.mark.parametrize(
    "after",
    [
        "Benefits:",
        "What we offer",
        "About us",
        "Responsibilities",
        "Про нас",
        "О компании",
        "Ofrecemos",
        "Responsabilidades",
    ],
)
def test_a_section_after_the_requirements_is_not_read_as_requirements(
    after: str,
) -> None:
    text = f"Requirements:\nPython\n{after}\nKubernetes budget"
    result = extract_requirements(text)
    assert (result.must, result.nice, result.text) == (("Python",), (), "Python")


def test_text_before_the_first_heading_is_not_a_requirement() -> None:
    result = extract_requirements("We use Docker.\nRequirements\nPython")
    assert (result.must, result.text) == (("Python",), "Python")


def test_a_requirement_section_can_resume_after_another_one() -> None:
    text = "Requirements\nPython\nBenefits\nFree lunch\nNice to have\nDocker"
    result = extract_requirements(text)
    assert result.text == "Python\nDocker"


def test_text_after_a_colon_on_the_heading_line_belongs_to_the_section() -> None:
    result = extract_requirements("Requirements: Python, Docker\nBenefits\nRedis")
    assert (set(result.must), result.text) == ({"Python", "Docker"}, "Python, Docker")


def test_a_bullet_that_starts_with_a_heading_word_is_not_a_heading() -> None:
    result = extract_requirements("Requirements:\n- Requirements gathering with Kafka")
    assert result.must == ("Kafka",)


def test_a_long_line_is_not_a_heading() -> None:
    line = "Requirements engineering experience on large regulated Kafka platforms"
    result = extract_requirements(f"Requirements:\n{line}")
    assert result.must == ("Kafka",)


@pytest.mark.parametrize(
    ("text", "low", "high"),
    [
        ("Salary: €60–80k", 60_000, 80_000),
        ("Salary: €60,000–80,000", 60_000, 80_000),
        ("€60,000 - €80,000 per year", 60_000, 80_000),
        ("Salary 60k EUR", 60_000, 60_000),
        ("EUR 70,000-90,000 gross", 70_000, 90_000),
        ("up to €75k a year", 75_000, 75_000),
        ("€60k–€80k", 60_000, 80_000),
        ("€60.000", 60_000, 60_000),
        ("between 45.600 EUR and 61.800 EUR", 45_600, 61_800),
        ("€50k to €70k", 50_000, 70_000),
        ("45,000 to 61,000 EUR", 45_000, 61_000),
    ],
)
def test_an_annual_eur_salary_is_parsed(text: str, low: int, high: int) -> None:
    assert parse_salary_eur(text) == SalaryRange(low, high)


@pytest.mark.parametrize(
    "text",
    [
        "$5000",
        "5000 USD",
        "$60-80k",
        "£70,000",
        "No salary mentioned, 5 years of Python",
        "€50 per hour",
        "€5,000 per month",
        "€15,000 per month",
        "€12k/month",
        "€5000",
        "1,000 EUR development budget",
        "Founded in 2010, 2024 EUR",
        "",
    ],
)
def test_anything_but_an_annual_eur_salary_is_none(text: str) -> None:
    assert parse_salary_eur(text) is None


def test_the_first_valid_salary_wins_over_an_earlier_non_annual_one() -> None:
    text = "Bonus €500 per month, base €60–80k"
    assert parse_salary_eur(text) == SalaryRange(60_000, 80_000)


@pytest.mark.parametrize(
    "text",
    [
        "Proficient in Go",
        "Go, Python",
        "Strong Go/Rust background",
        "Backend (Go)",
    ],
)
def test_go_matches_as_a_capitalised_word(text: str) -> None:
    assert "Go" in find_terms(text)


@pytest.mark.parametrize(
    "text",
    [
        "Google Cloud experience",
        "We go the extra mile",
        "Own the go-to-market plan",
        "Go-to-market strategy",
        "Gopher",
        "Django",
    ],
)
def test_go_does_not_match_inside_words_or_in_prose(text: str) -> None:
    assert "Go" not in find_terms(text)


@pytest.mark.parametrize(
    ("text", "term"),
    [
        ("Experience in C++ and Rust", "C++"),
        ("C# developer", "C#"),
        ("Senior .NET engineer", ".NET"),
        ("CI/CD pipelines", "CI/CD"),
        ("Spring Boot services", "Spring"),
        ("Apache Kafka", "Kafka"),
    ],
)
def test_terms_with_symbols_and_multi_word_synonyms_are_found(
    text: str, term: str
) -> None:
    assert term in find_terms(text)


def test_a_cased_symbol_term_is_not_found_inside_a_longer_word() -> None:
    assert find_terms("ASP.NET and Objective-C++ and C#sharp") == ()


def test_text_without_dictionary_terms_gives_nothing() -> None:
    assert find_terms("A friendly team with a great culture") == ()


def test_each_term_is_reported_once() -> None:
    assert find_terms("Python, python, PYTHON") == ("Python",)


@pytest.mark.parametrize(
    ("title", "level"),
    [
        ("Senior Backend Engineer", Seniority.SENIOR),
        ("Sr. Engineer", Seniority.SENIOR),
        ("Sénior Developer", Seniority.SENIOR),
        ("Lead", Seniority.LEAD),
        ("Tech Lead, Payments", Seniority.LEAD),
        ("Senior Tech Lead", Seniority.LEAD),
        ("Principal Engineer", Seniority.PRINCIPAL),
        ("Junior Developer", Seniority.JUNIOR),
        ("Jr. Developer", Seniority.JUNIOR),
        ("Mid-level Engineer", Seniority.MIDDLE),
        ("Middle Python Developer", Seniority.MIDDLE),
        ("Backend Engineer", None),
        ("Leadership Coach", None),
        ("Seniority Manager", None),
        ("", None),
    ],
)
def test_seniority_comes_from_the_title(title: str, level: Seniority | None) -> None:
    assert seniority_from_title(title) is level


def test_a_target_domain_found_in_the_text_is_reported() -> None:
    text = "We build payment infrastructure for Open Banking and fintech"
    domains = ("Fintech", "open banking", "healthcare")
    assert find_domains(text, domains) == ("Fintech", "open banking")


@pytest.mark.parametrize(
    ("text", "domain"),
    [
        ("We serve fintechs worldwide", "fintech"),
        ("Core payments platform", "payment"),
        ("A payment platform", "payments"),
        ("Bank infrastructure team", "banking"),
        ("Investment banking tools", "bank"),
        ("Digital banks and neobanks", "bank"),
        ("We love open-banking APIs", "open banking"),
    ],
)
def test_a_target_domain_matches_the_plural_or_stem_of_a_word_in_the_text(
    text: str, domain: str
) -> None:
    assert find_domains(text, (domain,)) == (domain,)


@pytest.mark.parametrize(
    ("text", "domain"),
    [
        ("Bankruptcy lawyers", "bank"),
        ("Fintechnology park", "fintech"),
        ("Unpaid internship", "payment"),
        ("Business class", "bus"),
    ],
)
def test_a_target_domain_does_not_match_inside_other_words(
    text: str, domain: str
) -> None:
    assert find_domains(text, (domain,)) == ()


def test_a_target_domain_missing_from_the_text_is_not_reported() -> None:
    assert find_domains("We sell shoes online", ("fintech", "")) == ()


def test_fact_texts_yield_the_dictionary_terms_they_mention() -> None:
    facts = ["Built services in Go and postgres", "Deployed to k8s", "Wrote Go tools"]
    assert set(terms_in_facts(facts)) == {"Go", "PostgreSQL", "Kubernetes"}
    assert len(terms_in_facts(facts)) == 3


def test_facts_without_terms_or_an_empty_list_yield_nothing() -> None:
    assert terms_in_facts(["Led a team of five", "Mentored juniors"]) == ()
    assert terms_in_facts([]) == ()
