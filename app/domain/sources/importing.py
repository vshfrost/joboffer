"""Підсумок імпорту вакансій одного джерела."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Self


class Outcome(StrEnum):
    """Що сталося з однією вакансією джерела."""

    IMPORTED = "imported"
    # Вакансія з алерту LinkedIn без тексту отримала текст із джерела.
    COMPLETED = "completed"
    DUPLICATE = "duplicate"
    # Не пройшла фільтр профілю.
    FILTERED = "filtered"


@dataclass(frozen=True, slots=True)
class ImportSummary:
    found: int = 0
    imported: int = 0
    filtered: int = 0
    duplicate: int = 0
    completed: int = 0

    @classmethod
    def of(cls, outcomes: Sequence[Outcome]) -> Self:
        return cls(
            found=len(outcomes),
            imported=outcomes.count(Outcome.IMPORTED),
            filtered=outcomes.count(Outcome.FILTERED),
            duplicate=outcomes.count(Outcome.DUPLICATE),
            completed=outcomes.count(Outcome.COMPLETED),
        )
