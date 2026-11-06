"""Прогін джерел: що читати, чим закінчилось читання одного джерела користувача."""

from dataclasses import dataclass, field
from datetime import datetime

from domain.identity.ids import UserId
from domain.sources.failure import FailureReason
from domain.sources.ids import SourceId
from domain.sources.importing import ImportSummary
from domain.sources.kinds import SourceKind
from domain.sources.target import SourceTarget


@dataclass(frozen=True, slots=True)
class Subscription:
    """Увімкнене джерело одного користувача: його компанія ATS чи RSS-стрічка."""

    id: SourceId
    user_id: UserId
    kind: SourceKind
    # Слаг компанії; для стрічки — параметри запиту.
    ref: str
    # Назва компанії в користувача; для стрічок порожньо.
    name: str = ""

    @property
    def target(self) -> SourceTarget:
        return SourceTarget(self.kind, self.ref, self.name)


@dataclass(frozen=True, slots=True)
class SourceRun:
    """Останній прогін джерела користувача: час, лічильники й код помилки (`None` — вдалося)."""

    ran_at: datetime
    summary: ImportSummary = field(default_factory=ImportSummary)
    error: FailureReason | None = None


@dataclass(frozen=True, slots=True)
class SubscriptionRun:
    subscription: Subscription
    run: SourceRun


@dataclass(slots=True)
class RefreshReport:
    # Інший прогін ще йде — цей нічого не читав і не писав.
    locked: bool = False
    # Скільки різних цілей прочитано (та сама ціль кількох користувачів — одна).
    targets: int = 0
    runs: list[SubscriptionRun] = field(default_factory=list)
