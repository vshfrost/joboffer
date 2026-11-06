"""Гейт CV перед подачею: два числа й рішення. Лише показує, чи CV готове; зберігання не блокує."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum

from domain.analysis.keywords import KeywordFacts, requirement_key
from domain.documents.lint import KeywordCoverage, keyword_coverage

# Перше число: усі слова вакансії, під якими є підтверджений факт, мусять бути в CV.
EVIDENCE_THRESHOLD = 100
# Друге число: покриття очищеного списку слів аналізу (групи «a | b» — одна вимога, дублі злиті).
COVERAGE_THRESHOLD = 90


class GateStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    # Аналіз старий (без карти фактів) чи без слів: «пройдено» казати не можна.
    NO_DATA = "no_data"


@dataclass(frozen=True, slots=True)
class CvGate:
    status: GateStatus
    evidence_percent: int | None
    evidence_missing: tuple[str, ...]
    coverage_percent: int | None


def cv_gate(
    coverage: KeywordCoverage | None,
    keyword_facts: Sequence[KeywordFacts] | None,
    live_facts: Collection[int],
) -> CvGate:
    """`live_facts` — номери підтверджених фактів, що існують зараз: непідтверджений чи видалений
    факт слова не підтверджує. Слово з карти шукається серед слів покриття за вимогою
    (`requirement_key`), тож злиті дублі не губляться."""
    if coverage is None:
        return CvGate(GateStatus.NO_DATA, None, (), None)
    if keyword_facts is None:
        return CvGate(GateStatus.NO_DATA, None, (), coverage.percent)
    live = set(live_facts)
    backed = {
        requirement_key(item.keyword)
        for item in keyword_facts
        if live.intersection(item.fact_numbers)
    }
    present = [word for word in coverage.covered if requirement_key(word) in backed]
    missing = tuple(
        word for word in coverage.missing if requirement_key(word) in backed
    )
    total = len(present) + len(missing)
    # Вниз, не за округленням: одне слово з двохсот не має виглядати як 100.
    evidence = 100 * len(present) // total if total else 100
    passed = evidence >= EVIDENCE_THRESHOLD and coverage.meets(COVERAGE_THRESHOLD)
    return CvGate(
        GateStatus.PASSED if passed else GateStatus.FAILED,
        evidence,
        missing,
        coverage.percent,
    )


@dataclass(frozen=True, slots=True)
class CvCeiling:
    """Найбільше покриття, яке CV під цю вакансію може мати чесно: лише слова з підтвердженим фактом."""

    percent: int
    unbacked: tuple[str, ...]
    reaches_target: bool


def cv_ceiling(
    keywords: Sequence[str],
    keyword_facts: Sequence[KeywordFacts] | None,
    live_facts: Collection[int],
) -> CvCeiling | None:
    """None — карти фактів чи слів нема (старий аналіз): стелі казати не можна."""
    empty = keyword_coverage(tuple(keywords), ())
    if empty is None or keyword_facts is None:
        return None
    live = set(live_facts)
    backed = {
        requirement_key(item.keyword)
        for item in keyword_facts
        if live.intersection(item.fact_numbers)
    }
    # Очищений список слів аналізу (групи й дублі злиті) — той самий, що рахує гейт.
    words = empty.missing
    unbacked = tuple(word for word in words if requirement_key(word) not in backed)
    have = len(words) - len(unbacked)
    return CvCeiling(
        100 * have // len(words),
        unbacked,
        100 * have >= COVERAGE_THRESHOLD * len(words),
    )
