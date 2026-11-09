"""Покриття must-have вимог аналізу рядками CV: агент називає, які факти стоять під пунктом (прямо чи
як аналог), сервер перевіряє, що факти справжні й що CV на них справді спирається."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum


class MustHaveKind(StrEnum):
    """Як факти закривають пункт: самі вимоги (`fact`) чи схожий досвід замість неї (`analogue`)."""

    FACT = "fact"
    ANALOGUE = "analogue"


class MustHaveStatus(StrEnum):
    COVERED = "covered"
    ANALOGUE = "analogue"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class MustHaveEntry:
    """Що агент каже про пункт: його текст, факти під ним і як вони його закривають."""

    item: str
    fact_ids: tuple[int, ...]
    kind: MustHaveKind


@dataclass(frozen=True, slots=True)
class MustHaveItem:
    item: str
    status: MustHaveStatus
    # Факти запису, на які спирається рядок CV; порожньо для `missing`.
    fact_ids: tuple[int, ...]
    reason: str | None


@dataclass(frozen=True, slots=True)
class MustHaveCoverage:
    items: tuple[MustHaveItem, ...]
    # Пункти з записів, яких в аналізі нема: не помилка.
    unknown: tuple[str, ...]


NO_ENTRY = "У must_have_facts немає запису для цього пункту."

# Статус за видом чинного запису; `fact` сильніший за `analogue`.
_STATUS = {
    MustHaveKind.FACT: MustHaveStatus.COVERED,
    MustHaveKind.ANALOGUE: MustHaveStatus.ANALOGUE,
}


def _same(item: str) -> str:
    return " ".join(item.split()).casefold()


def must_have_coverage(
    must_have: Sequence[str],
    entries: Sequence[MustHaveEntry],
    cited: Collection[int],
    live: Collection[int],
) -> MustHaveCoverage:
    """`cited` — факти, на які спираються рядки CV; `live` — номери підтверджених фактів
    користувача. Пункт збігається із записом без урахування регістру й пробілів. Запис чинний, лише
    коли всі його факти підтверджені й хоч один із них у `cited`; серед чинних `fact` дає
    `covered`, `analogue` — `analogue`; без чинних пункт `missing` з причиною першого запису."""
    wanted = {_same(item) for item in must_have}
    unknown = tuple(
        dict.fromkeys(
            entry.item for entry in entries if _same(entry.item) not in wanted
        )
    )
    return MustHaveCoverage(
        tuple(_item(item, entries, cited, live) for item in must_have), unknown
    )


def _item(
    item: str,
    entries: Sequence[MustHaveEntry],
    cited: Collection[int],
    live: Collection[int],
) -> MustHaveItem:
    failures: list[str] = []
    valid: dict[MustHaveKind, tuple[int, ...]] = {}
    for entry in entries:
        if _same(entry.item) != _same(item):
            continue
        ids = tuple(dict.fromkeys(entry.fact_ids))
        dead = [fact for fact in ids if fact not in live]
        used = tuple(fact for fact in ids if fact in cited)
        if dead:
            failures.append(f"Факти {dead} не є підтвердженими фактами користувача.")
        elif not used:
            failures.append(f"Жоден рядок CV не спирається на факти {list(ids)}.")
        else:
            valid.setdefault(entry.kind, used)
    for kind in MustHaveKind:
        if kind in valid:
            return MustHaveItem(item, _STATUS[kind], valid[kind], None)
    return MustHaveItem(
        item, MustHaveStatus.MISSING, (), failures[0] if failures else NO_ENTRY
    )
