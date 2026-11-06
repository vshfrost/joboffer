"""Одне джерело правил тріажу: числа й вердикти в `prompts/triage/rules.md` (для агента) збігаються
з константами `domain/triage/scoring.py` (для cron). Змінив поріг чи бал у коді — зміни й промпт."""

import re
from pathlib import Path

import pytest

from application.ports.prompts import PromptKey
from domain.triage import scoring
from domain.triage.scoring import Mismatch
from domain.triage.triage import (
    AGENT_BATCH,
    MAX_REASON_LENGTH,
    MAX_SCORE,
    MIN_SCORE,
)
from infrastructure.prompts.catalog import FilePrompts

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
RULES = FilePrompts.load(CATALOG).get(PromptKey.TRIAGE_RULES)

# Фраза в правилах для кожної жорсткої невідповідності: нова невідповідність у коді без фрази тут
# і в правилах провалить тест.
MISMATCH_PHRASES = {
    Mismatch.FORMAT: "work mode or location outside the profile",
    Mismatch.LEVEL: "seniority level outside the profile",
    Mismatch.EXCLUDED_WORD: "a title word the profile excludes",
    Mismatch.SALARY: "salary stated and below the profile minimum",
    Mismatch.STOP_WORD: "a profile stop word",
}


def number_before(phrase: str) -> int:
    match = re.search(rf"(\d+) {re.escape(phrase)}", RULES)
    assert match, f"у правилах нема «<число> {phrase}»"
    return int(match.group(1))


def number_after(phrase: str) -> int:
    match = re.search(rf"{re.escape(phrase)} (\d+)", RULES)
    assert match, f"у правилах нема «{phrase} <число>»"
    return int(match.group(1))


def test_the_rubric_lines_are_40_20_15_10_10_5_in_the_order_of_the_code() -> None:
    rubric = [int(points) for points in re.findall(r"^- (\d+) — ", RULES, re.MULTILINE)]
    assert rubric == [
        scoring.MUST_POINTS,
        scoring.ROLE_POINTS + scoring.LEVEL_POINTS,
        scoring.FORMAT_POINTS,
        scoring.MAX_DOMAIN_POINTS,
        scoring.NICE_POINTS,
        scoring.SALARY_POINTS,
    ]
    assert rubric == [40, 20, 15, 10, 10, 5]
    assert sum(rubric) == 100


def test_the_partial_points_are_the_ones_of_the_code() -> None:
    assert number_before("when a title matches a profile role") == scoring.ROLE_POINTS
    assert number_before("when the level in the title fits") == scoring.LEVEL_POINTS
    assert (
        number_before("when the title names no level") == scoring.LEVEL_UNKNOWN_POINTS
    )
    assert (
        number_before("when the mode is not stated and the profile accepts it")
        == scoring.FORMAT_UNKNOWN_POINTS
    )
    assert (
        number_before("for each profile target domain the posting mentions")
        == scoring.DOMAIN_POINTS
    )
    assert number_after("not stated =") == scoring.SALARY_UNSTATED_POINTS


def test_the_neutral_and_keyword_points_are_the_ones_of_the_code() -> None:
    assert number_after("none recognised =") == scoring.MUST_NEUTRAL_POINTS
    assert (
        number_before("when the title has no role match but a profile title keyword")
        == scoring.ROLE_KEYWORD_POINTS
    )
    assert (scoring.MUST_NEUTRAL_POINTS, scoring.ROLE_KEYWORD_POINTS) == (20, 8)


def test_every_number_in_the_rules_is_a_constant_of_the_code() -> None:
    known = {
        MIN_SCORE,
        MAX_SCORE,
        MAX_REASON_LENGTH,
        AGENT_BATCH,
        scoring.MUST_POINTS,
        scoring.MUST_NEUTRAL_POINTS,
        scoring.ROLE_POINTS,
        scoring.ROLE_KEYWORD_POINTS,
        scoring.LEVEL_POINTS,
        scoring.LEVEL_UNKNOWN_POINTS,
        scoring.ROLE_POINTS + scoring.LEVEL_POINTS,
        scoring.FORMAT_POINTS,
        scoring.FORMAT_UNKNOWN_POINTS,
        scoring.DOMAIN_POINTS,
        scoring.MAX_DOMAIN_POINTS,
        scoring.NICE_POINTS,
        scoring.SALARY_POINTS,
        scoring.SALARY_UNSTATED_POINTS,
        scoring.ANALYSE_SCORE,
        scoring.SKIP_SCORE,
        scoring.MIN_RECOGNISED,
    }
    assert {int(n) for n in re.findall(r"\d+", RULES)} <= known


def test_the_rules_describe_the_calibration_of_the_code() -> None:
    assert "same hard filters as the analysis" in RULES
    assert "a remote posting passes in any place" in RULES
    assert "plural" in RULES
    assert re.search(
        r"fewer than \d+ recognised requirements never skip by score", RULES
    )


def test_the_domain_points_are_capped_at_the_code_maximum() -> None:
    match = re.search(r"mentions \(at most (\d+)\)", RULES)
    assert match
    assert int(match.group(1)) == scoring.MAX_DOMAIN_POINTS


def test_the_verdict_thresholds_are_the_ones_of_the_code() -> None:
    assert number_after("analyse — a score of") == scoring.ANALYSE_SCORE
    assert number_after("or a score below") == scoring.SKIP_SCORE
    assert number_after("at least") == scoring.MIN_RECOGNISED
    assert number_after("fewer than") == scoring.MIN_RECOGNISED
    assert (scoring.ANALYSE_SCORE, scoring.SKIP_SCORE, scoring.MIN_RECOGNISED) == (
        55,
        40,
        3,
    )


def test_the_score_and_reason_limits_are_the_ones_of_the_code() -> None:
    assert f"{MIN_SCORE}–{MAX_SCORE}" in RULES
    assert number_after("reason: at most") == MAX_REASON_LENGTH


@pytest.mark.parametrize("mismatch", list(Mismatch))
def test_every_hard_mismatch_of_the_code_is_named_in_the_rules(
    mismatch: Mismatch,
) -> None:
    assert MISMATCH_PHRASES[mismatch] in RULES


def test_the_rules_say_that_a_mismatch_always_means_skip() -> None:
    assert re.search(r"skip — .*mismatch", RULES)
    assert "no mismatch" in RULES


def test_the_rules_have_no_cyrillic_and_name_no_owner() -> None:
    assert not re.search("[А-Яа-яІіЇїЄєҐґ]", RULES)
    assert not re.search(r"\b(Taras|he|his|him|himself)\b", RULES)
