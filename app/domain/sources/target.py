"""Що саме читає адаптер: одна компанія ATS чи одна RSS-стрічка."""

from dataclasses import dataclass

from domain.sources.kinds import SourceKind


@dataclass(frozen=True, slots=True)
class SourceTarget:
    kind: SourceKind
    # Слаг компанії; для стрічки — параметри запиту («category=Python&remote»).
    ref: str
    # Назва компанії цілі; для стрічок порожньо (компанія береться з вакансії).
    name: str = ""
