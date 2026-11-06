"""Незмінний ланцюжок атомарних сценаріїв вакансії: кожен пропонує наступний.

Порядок — порядок членів `Scenario`. Крок може не знадобитися вакансії (`skip_reason`): тоді
ланцюжок не зупиняється, а наступний крок вираховується повз нього.
"""

from dataclasses import dataclass
from enum import StrEnum

from domain.shared.errors import InvalidValue


class Scenario(StrEnum):
    ADD_JOB = "add_job"
    ANALYSIS = "analysis"
    GAPS = "gaps"
    REANALYSIS = "reanalysis"
    CV = "cv"
    COVER_LETTER = "cover_letter"
    APPLY = "apply"


CHAIN: tuple[Scenario, ...] = tuple(Scenario)

NO_OPEN_GAPS = "no open gaps"
ANALYSIS_NOT_STALE = "the analysis is not stale"


@dataclass(frozen=True, slots=True)
class JobProgress:
    """Що відомо про вакансію для пропусків: відкриті прогалини й застарілий аналіз."""

    has_open_gaps: bool
    analysis_stale: bool


def parse_scenario(name: str) -> Scenario:
    """`InvalidValue` з переліком допустимих імен, коли сценарію з таким іменем нема."""
    try:
        return Scenario(name)
    except ValueError:
        valid = ", ".join(CHAIN)
        raise InvalidValue(
            "name", f"Невідомий сценарій «{name}». Доступні: {valid}."
        ) from None


def skip_reason(scenario: Scenario, progress: JobProgress) -> str | None:
    """Чому крок цій вакансії не потрібен; None — потрібен."""
    if scenario is Scenario.GAPS and not progress.has_open_gaps:
        return NO_OPEN_GAPS
    if scenario is Scenario.REANALYSIS and not progress.analysis_stale:
        return ANALYSIS_NOT_STALE
    return None


def next_after(scenario: Scenario, progress: JobProgress) -> Scenario | None:
    """Найближчий після `scenario` крок, який вакансії потрібен; None — ланцюжок закінчено."""
    for following in CHAIN[CHAIN.index(scenario) + 1 :]:
        if skip_reason(following, progress) is None:
            return following
    return None
