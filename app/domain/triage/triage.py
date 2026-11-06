"""Швидкий тріаж вакансій: Claude оцінює пачку за початком тексту й профілем (скор 0–100 і
вердикт), сервер лише валідує й зберігає. Повний аналіз від тріажу не залежить і має пріоритет у показі."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domain.shared.errors import InvalidValue

MIN_SCORE = 0
MAX_SCORE = 100
MAX_REASON_LENGTH = 160
# Скільки вакансій у пачці агента (`prepare_triage` / `save_triage`); пачка cron — `MAX_PER_USER`.
AGENT_BATCH = 5


class TriageSource(StrEnum):
    """Хто оцінив: Claude через MCP (`agent`) чи сервер за ключовими словами без LLM (`rules`)."""

    AGENT = "agent"
    RULES = "rules"


class TriageVerdict(StrEnum):
    SKIP = "skip"
    MAYBE = "maybe"
    ANALYSE = "analyse"


@dataclass(frozen=True, slots=True)
class TriageEntry:
    """Перевірений тріаж однієї вакансії (за її номером у межах користувача)."""

    job_number: int
    score: int
    verdict: TriageVerdict
    reason: str


@dataclass(frozen=True, slots=True)
class Triage:
    """Збережений тріаж вакансії."""

    job_number: int
    score: int
    verdict: TriageVerdict
    reason: str
    triaged_at: datetime
    source: TriageSource = TriageSource.AGENT


def parse_entry(
    position: int, job_number: int, score: int, verdict: str, reason: str
) -> TriageEntry:
    """Один елемент пачки; `position` — номер елемента (з 1) для повідомлення про помилку."""
    where = f"Елемент {position} (вакансія {job_number})"
    if not MIN_SCORE <= score <= MAX_SCORE:
        raise InvalidValue(
            "items", f"{where}: скор — ціле число від {MIN_SCORE} до {MAX_SCORE}."
        )
    try:
        parsed = TriageVerdict(verdict.strip())
    except ValueError:
        options = " | ".join(item.value for item in TriageVerdict)
        raise InvalidValue("items", f"{where}: вердикт — {options}.") from None
    text = " ".join(reason.split())
    if not text:
        raise InvalidValue("items", f"{where}: потрібна причина.")
    if len(text) > MAX_REASON_LENGTH:
        raise InvalidValue(
            "items", f"{where}: причина — до {MAX_REASON_LENGTH} символів."
        )
    return TriageEntry(job_number=job_number, score=score, verdict=parsed, reason=text)
