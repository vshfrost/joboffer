"""Команди й результати контексту facts: примітиви (значення будує use case)."""

from dataclasses import dataclass
from datetime import datetime

from domain.facts.fact import FactKind, FactSource
from domain.facts.library import FactCounts


@dataclass(frozen=True, slots=True, kw_only=True)
class FactInput:
    """Сирі значення з будь-якого транспорту; розбір і валідація — у домені."""

    kind: str = ""
    text: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class FactData:
    fact_number: int
    kind: FactKind
    text: str
    confirmed: bool
    created_at: datetime
    updated_at: datetime
    source: FactSource = FactSource.CV
    job_id: int | None = None


@dataclass(frozen=True, slots=True)
class SavedFactsData:
    added: tuple[FactData, ...]
    # Тексти, що вже були (у базі чи раніше в тій самій пачці), — пропущені.
    skipped: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FactLibraryData:
    facts: tuple[FactData, ...]
    counts: FactCounts


@dataclass(frozen=True, slots=True, kw_only=True)
class OriginalCvData:
    text: str
    file_name: str | None
    saved_at: datetime
