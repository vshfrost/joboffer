"""Гейт CV: перше число — слова з фактом, що є в CV (треба 100); друге — покриття очищеного списку
слів (треба 90). «Немає даних» — не «пройдено»."""

from domain.analysis.keywords import KeywordFacts
from domain.documents.gate import CvGate, GateStatus, cv_gate
from domain.documents.lint import keyword_coverage


def gate(
    keywords: tuple[str, ...],
    cv_words: tuple[str, ...],
    backed: dict[str, tuple[int, ...]] | None,
    live: tuple[int, ...] = (1, 2),
) -> CvGate:
    coverage = keyword_coverage(keywords, (" ".join(cv_words),))
    facts = (
        None
        if backed is None
        else tuple(KeywordFacts(word, numbers) for word, numbers in backed.items())
    )
    return cv_gate(coverage, facts, live)


def numbered(count: int) -> tuple[str, ...]:
    return tuple(f"w{number:02d}" for number in range(count))


def test_all_backed_words_in_the_cv_give_100_and_name_nothing() -> None:
    result = gate(
        ("Python", "Kafka"), ("Python", "Kafka"), {"Python": (1,), "Kafka": (2,)}
    )

    assert (result.evidence_percent, result.evidence_missing) == (100, ())


def test_a_backed_word_missing_from_the_cv_is_below_100_and_named() -> None:
    result = gate(("Python", "Kafka"), ("Python",), {"Python": (1,), "Kafka": (2,)})

    assert (result.evidence_percent, result.evidence_missing) == (50, ("Kafka",))
    assert result.status is GateStatus.FAILED


def test_one_missing_backed_word_of_two_hundred_is_never_rounded_up_to_100() -> None:
    words = numbered(200)
    result = gate(words, words[1:], dict.fromkeys(words, (1,)))

    assert (result.evidence_percent, result.evidence_missing) == (99, ("w00",))


def test_an_unconfirmed_fact_does_not_back_a_word() -> None:
    # Факт 2 існує, але непідтверджений: серед живих (підтверджених) його нема.
    result = gate(
        ("Python", "Kafka"), ("Python",), {"Python": (1,), "Kafka": (2,)}, live=(1,)
    )

    assert (result.evidence_percent, result.evidence_missing) == (100, ())


def test_a_deleted_fact_does_not_back_a_word() -> None:
    result = gate(("Python", "Kafka"), ("Python",), {"Python": (1,), "Kafka": (7,)})

    assert (result.evidence_percent, result.evidence_missing) == (100, ())


def test_one_live_fact_among_several_is_enough_to_back_a_word() -> None:
    result = gate(("Kafka",), (), {"Kafka": (7, 2)})

    assert (result.evidence_percent, result.evidence_missing) == (0, ("Kafka",))


def test_a_group_is_one_backed_word_covered_by_any_spelling() -> None:
    result = gate(
        ("Java | Python", "Kafka"),
        ("Python", "Kafka"),
        {"Java | Python": (1,), "Kafka": (2,)},
    )

    assert (result.evidence_percent, result.evidence_missing) == (100, ())


def test_the_map_key_is_matched_to_the_keyword_ignoring_case_and_spacing() -> None:
    result = gate(("Java | Python",), (), {"python|JAVA": (1,)})

    assert result.evidence_missing == ("Java | Python",)


def test_18_of_20_words_in_the_cv_pass_the_threshold_90() -> None:
    words = numbered(20)
    result = gate(words, words[:18], {"w00": (1,)})

    assert (result.coverage_percent, result.status) == (90, GateStatus.PASSED)


def test_17_of_20_words_in_the_cv_do_not_pass() -> None:
    words = numbered(20)
    result = gate(words, words[:17], {"w00": (1,)})

    assert (result.coverage_percent, result.status) == (85, GateStatus.FAILED)


def test_43_of_48_rounds_to_90_but_is_below_the_threshold() -> None:
    words = numbered(48)
    result = gate(words, words[:43], {"w00": (1,)})

    assert (result.coverage_percent, result.status) == (90, GateStatus.FAILED)


def test_coverage_95_does_not_pass_while_a_backed_word_is_missing() -> None:
    words = numbered(20)
    result = gate(words, words[:19], {"w19": (1,)})

    assert (result.coverage_percent, result.evidence_missing) == (95, ("w19",))
    assert result.status is GateStatus.FAILED


def test_an_analysis_without_the_map_has_no_data_not_passed() -> None:
    result = gate(("Python",), ("Python",), None)

    assert result == CvGate(GateStatus.NO_DATA, None, (), 100)


def test_an_analysis_without_keywords_has_no_data() -> None:
    result = cv_gate(None, (KeywordFacts("Python", (1,)),), (1,))

    assert result == CvGate(GateStatus.NO_DATA, None, (), None)


def test_a_map_where_no_word_has_a_live_fact_passes_on_evidence_by_default() -> None:
    result = gate(("Python",), ("Python",), {"Python": (9,)})

    assert (result.evidence_percent, result.status) == (100, GateStatus.PASSED)
