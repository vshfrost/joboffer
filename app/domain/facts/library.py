"""Бібліотека фактів: порядок показу й лічильники за видами та статусом."""

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from domain.facts.fact import Fact, FactKind
from domain.shared.errors import InvalidValue


@dataclass(frozen=True, slots=True)
class KindCount:
    kind: FactKind
    total: int
    confirmed: int
    unconfirmed: int


@dataclass(frozen=True, slots=True)
class FactCounts:
    total: int
    confirmed: int
    unconfirmed: int
    # Усі види в порядку секцій, навіть порожні.
    kinds: tuple[KindCount, ...]


_KIND_ORDER = {kind: position for position, kind in enumerate(FactKind)}


def ordered(facts: Iterable[Fact]) -> list[Fact]:
    """За видами (порядок `FactKind`), усередині виду — в порядку додавання."""
    return sorted(facts, key=lambda fact: (_KIND_ORDER[fact.kind], fact.number))


def count_facts(facts: Iterable[Fact]) -> FactCounts:
    found = list(facts)
    kinds = tuple(
        _kind_count(kind, [fact for fact in found if fact.kind is kind])
        for kind in FactKind
    )
    confirmed = sum(1 for fact in found if fact.confirmed)
    return FactCounts(
        total=len(found),
        confirmed=confirmed,
        unconfirmed=len(found) - confirmed,
        kinds=kinds,
    )


def _kind_count(kind: FactKind, facts: list[Fact]) -> KindCount:
    confirmed = sum(1 for fact in facts if fact.confirmed)
    return KindCount(kind, len(facts), confirmed, len(facts) - confirmed)


def confirmed(facts: Iterable[Fact]) -> list[Fact]:
    """Лише підтверджені, у порядку `ordered`."""
    return ordered(fact for fact in facts if fact.confirmed)


def require_confirmed(facts: Iterable[Fact], numbers: Collection[int]) -> None:
    """Кожен номер — підтверджений факт із `facts` (факти користувача), інакше `InvalidValue`:
    на невідомому, чужому чи непідтвердженому факті не стоїть жоден рядок документа."""
    known = {fact.number: fact for fact in facts}
    require_existing(known, numbers, "fact_ids")
    unconfirmed = sorted(number for number in numbers if not known[number].confirmed)
    if unconfirmed:
        raise InvalidValue(
            "fact_ids",
            f"Факти не підтверджені: {_numbers(unconfirmed)} — "
            "спершу користувач їх підтверджує.",
        )


def require_existing(
    known: Collection[int], numbers: Collection[int], field: str
) -> None:
    """Кожен номер — факт із `known` (факти користувача), інакше `InvalidValue` на полі `field`."""
    missing = sorted(set(numbers) - set(known))
    if missing:
        raise InvalidValue(field, f"Факти не знайдено: {_numbers(missing)}.")


def _numbers(numbers: list[int]) -> str:
    return ", ".join(f"#{number}" for number in numbers)
