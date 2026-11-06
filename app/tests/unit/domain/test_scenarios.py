"""Ланцюжок сценаріїв вакансії: незмінний порядок, пропуски й наступний крок."""

import pytest

from domain.scenarios.chain import (
    CHAIN,
    JobProgress,
    Scenario,
    next_after,
    parse_scenario,
    skip_reason,
)
from domain.shared.errors import InvalidValue

ORDER = ["add_job", "analysis", "gaps", "reanalysis", "cv", "cover_letter", "apply"]

FRESH = JobProgress(has_open_gaps=False, analysis_stale=False)
OPEN_GAPS = JobProgress(has_open_gaps=True, analysis_stale=False)
STALE = JobProgress(has_open_gaps=False, analysis_stale=True)
BOTH = JobProgress(has_open_gaps=True, analysis_stale=True)


def test_the_chain_order_is_exactly_the_agreed_one() -> None:
    assert [scenario.value for scenario in CHAIN] == ORDER


def test_nothing_follows_apply() -> None:
    for progress in (FRESH, OPEN_GAPS, STALE, BOTH):
        assert next_after(Scenario.APPLY, progress) is None


@pytest.mark.parametrize("name", ORDER)
def test_a_known_name_is_parsed(name: str) -> None:
    assert parse_scenario(name).value == name


def test_an_unknown_name_is_refused_and_the_valid_names_are_listed() -> None:
    with pytest.raises(InvalidValue) as error:
        parse_scenario("interview")

    assert error.value.field == "name"
    assert "interview" in error.value.message
    for name in ORDER:
        assert name in error.value.message


def test_gaps_are_required_when_there_are_open_gaps() -> None:
    assert skip_reason(Scenario.GAPS, OPEN_GAPS) is None


def test_gaps_are_skipped_when_there_are_no_open_gaps() -> None:
    assert skip_reason(Scenario.GAPS, FRESH) == "no open gaps"


def test_reanalysis_is_required_when_the_analysis_is_stale() -> None:
    assert skip_reason(Scenario.REANALYSIS, STALE) is None


def test_reanalysis_is_skipped_when_the_analysis_is_fresh() -> None:
    assert skip_reason(Scenario.REANALYSIS, FRESH) == "the analysis is not stale"


@pytest.mark.parametrize(
    "scenario",
    [
        Scenario.ADD_JOB,
        Scenario.ANALYSIS,
        Scenario.CV,
        Scenario.COVER_LETTER,
        Scenario.APPLY,
    ],
)
@pytest.mark.parametrize("progress", [FRESH, OPEN_GAPS, STALE, BOTH])
def test_the_other_steps_are_never_skipped(
    scenario: Scenario, progress: JobProgress
) -> None:
    assert skip_reason(scenario, progress) is None


@pytest.mark.parametrize(
    ("scenario", "progress", "expected"),
    [
        (Scenario.ADD_JOB, FRESH, "analysis"),
        (Scenario.ANALYSIS, OPEN_GAPS, "gaps"),
        (Scenario.ANALYSIS, STALE, "reanalysis"),
        (Scenario.ANALYSIS, FRESH, "cv"),
        (Scenario.GAPS, STALE, "reanalysis"),
        (Scenario.GAPS, FRESH, "cv"),
        (Scenario.REANALYSIS, FRESH, "cv"),
        (Scenario.CV, FRESH, "cover_letter"),
        (Scenario.COVER_LETTER, FRESH, "apply"),
    ],
)
def test_the_next_step_passes_over_skipped_ones(
    scenario: Scenario, progress: JobProgress, expected: str
) -> None:
    following = next_after(scenario, progress)

    assert following is not None
    assert following.value == expected
