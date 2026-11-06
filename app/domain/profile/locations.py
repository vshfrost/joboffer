"""Локації пошуку: глобальні формати, місця із синонімами й форматами, невідомий формат, релокація."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self

from domain.profile.modes import WorkMode, parse_members
from domain.profile.text import one_line, unique_lines
from domain.shared.problems import Problems

MAX_PLACE_LENGTH = 100
MAX_ALIASES = 20
MAX_LOCATIONS = 50
UNKNOWN_MODE = "Невідомий формат роботи."
PLACE_MESSAGE = f"Місце — від 1 до {MAX_PLACE_LENGTH} символів, напр. Valencia."


@dataclass(frozen=True, slots=True)
class LocationDraft:
    """Рядок локації з вводу: ще не перевірений."""

    place: str
    aliases: Sequence[str]
    work_modes: Sequence[str]


@dataclass(frozen=True, slots=True)
class SearchLocation:
    place: str
    aliases: tuple[str, ...]
    work_modes: frozenset[WorkMode]


@dataclass(frozen=True, slots=True)
class Locations:
    work_modes: frozenset[WorkMode] = frozenset()
    locations: tuple[SearchLocation, ...] = ()
    include_unknown_mode: bool = True
    relocation: bool = False

    @classmethod
    def parse(
        cls,
        *,
        work_modes: Sequence[str],
        locations: Sequence[LocationDraft],
        include_unknown_mode: bool,
        relocation: bool,
    ) -> Self:
        problems = Problems()
        modes = parse_members(WorkMode, work_modes)
        if modes is None:
            problems.add("work_modes", UNKNOWN_MODE)
        rows = [_normalized(index, draft) for index, draft in enumerate(locations)]
        filled = [row for row in rows if row is not None]
        if len(filled) > MAX_LOCATIONS:
            problems.add("locations", f"Локацій пошуку — до {MAX_LOCATIONS}.")
        seen: set[str] = set()
        parsed: list[SearchLocation] = []
        for row in filled:
            location = _parse_row(row, seen, problems)
            if location is not None:
                parsed.append(location)
        problems.raise_if_any()
        return cls(
            work_modes=modes or frozenset(),
            locations=tuple(parsed),
            include_unknown_mode=include_unknown_mode,
            relocation=relocation,
        )


@dataclass(frozen=True, slots=True)
class _Row:
    """Рядок локації після нормалізації; `index` — його місце у вводі (для шляху помилки)."""

    index: int
    place: str
    aliases: tuple[str, ...]
    work_modes: Sequence[str]


def _normalized(index: int, draft: LocationDraft) -> _Row | None:
    """Рядок без місця й синонімів — порожній рядок форми: пропускається."""
    place = one_line(draft.place)
    aliases = tuple(
        alias
        for alias in unique_lines(one_line(alias) for alias in draft.aliases)
        if alias.casefold() != place.casefold()
    )
    if not place and not aliases:
        return None
    return _Row(index, place, aliases, draft.work_modes)


def _parse_row(row: _Row, seen: set[str], problems: Problems) -> SearchLocation | None:
    where = f"locations.{row.index}"
    place, aliases = row.place, row.aliases
    if not place or len(place) > MAX_PLACE_LENGTH:
        problems.add(f"{where}.place", PLACE_MESSAGE)
    elif place.casefold() in seen:
        problems.add(
            f"{where}.place", "Місця в локаціях пошуку не мають повторюватись."
        )
    else:
        seen.add(place.casefold())
    if len(aliases) > MAX_ALIASES or any(len(a) > MAX_PLACE_LENGTH for a in aliases):
        problems.add(
            f"{where}.aliases",
            f"Синонімів місця «{place}» — до {MAX_ALIASES}, кожен до {MAX_PLACE_LENGTH} символів.",
        )
    modes = parse_members(WorkMode, row.work_modes)
    if modes is None:
        problems.add(f"{where}.work_modes", UNKNOWN_MODE)
        return None
    if not modes:
        problems.add(
            f"{where}.work_modes",
            f"Для місця «{place}» обери хоч один формат: remote, hybrid чи onsite.",
        )
    return SearchLocation(place=place, aliases=aliases, work_modes=modes)
