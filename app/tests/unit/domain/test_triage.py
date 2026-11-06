"""Тріаж: межі скору, вердикти, причина — тексти помилок як у v1 (`origin/main` `99a2007`)."""

import pytest

from domain.shared.errors import InvalidValue
from domain.triage.triage import (
    AGENT_BATCH,
    MAX_REASON_LENGTH,
    TriageEntry,
    TriageSource,
    TriageVerdict,
    parse_entry,
)


def test_the_agent_batch_is_5_and_the_reason_limit_is_160() -> None:
    assert (AGENT_BATCH, MAX_REASON_LENGTH) == (5, 160)


def test_a_triage_is_rated_by_the_agent_or_by_the_rules() -> None:
    assert [source.value for source in TriageSource] == ["agent", "rules"]


def test_verdicts_are_skip_maybe_analyse() -> None:
    assert [verdict.value for verdict in TriageVerdict] == ["skip", "maybe", "analyse"]


def test_a_valid_item_becomes_an_entry() -> None:
    entry = parse_entry(1, 7, 72, "analyse", "Senior Python, remote")
    assert entry == TriageEntry(7, 72, TriageVerdict.ANALYSE, "Senior Python, remote")


@pytest.mark.parametrize("score", [0, 100])
def test_the_score_bounds_are_valid(score: int) -> None:
    assert parse_entry(1, 7, score, "maybe", "ok").score == score


@pytest.mark.parametrize("score", [-1, 101])
def test_a_score_outside_0_to_100_names_the_item(score: int) -> None:
    with pytest.raises(InvalidValue) as error:
        parse_entry(2, 7, score, "maybe", "ok")
    assert error.value.message == (
        "Елемент 2 (вакансія 7): скор — ціле число від 0 до 100."
    )


def test_an_unknown_verdict_lists_the_allowed_ones() -> None:
    with pytest.raises(InvalidValue) as error:
        parse_entry(3, 9, 50, "great", "ok")
    assert error.value.message == (
        "Елемент 3 (вакансія 9): вердикт — skip | maybe | analyse."
    )


def test_the_verdict_may_have_surrounding_spaces() -> None:
    assert parse_entry(1, 7, 50, " skip ", "ok").verdict is TriageVerdict.SKIP


@pytest.mark.parametrize("reason", ["", "   ", "\n\t"])
def test_a_blank_reason_is_rejected(reason: str) -> None:
    with pytest.raises(InvalidValue) as error:
        parse_entry(1, 7, 50, "skip", reason)
    assert error.value.message == "Елемент 1 (вакансія 7): потрібна причина."


def test_the_reason_is_collapsed_to_one_line() -> None:
    entry = parse_entry(1, 7, 50, "skip", "  Onsite \n in   Berlin ")
    assert entry.reason == "Onsite in Berlin"


def test_a_reason_of_160_characters_is_valid_and_161_is_not() -> None:
    assert len(parse_entry(1, 7, 50, "skip", "x" * 160).reason) == 160
    with pytest.raises(InvalidValue) as error:
        parse_entry(1, 7, 50, "skip", "x" * 161)
    assert error.value.message == "Елемент 1 (вакансія 7): причина — до 160 символів."
