"""План теми підготовки: кроки learn → practice → check, їхні межі та нотатка про виконання.

План пише Claude, користувач погоджує. Невиконані кроки заміняються разом, виконані лишаються
попереду й рахуються в межі плану (3–12 кроків, хоч один practice і один check). Помилки розбору
кроку — без номера: його додає use case, що знає позицію.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self

from domain.prep.ids import StepId
from domain.shared.errors import InvalidValue
from domain.shared.text import one_line

MIN_STEPS = 3
MAX_STEPS = 12
MAX_STEP_TITLE_LENGTH = 200
MAX_STEP_DETAILS_LENGTH = 2000
MAX_RESOURCES = 10
MAX_RESOURCE_TITLE_LENGTH = 200
MAX_URL_LENGTH = 500
MAX_STEP_MINUTES = 480
MAX_NOTE_LENGTH = 2000
# Схема http(s) і непорожній хост (домен не імпортує urllib).
WEB_LINK = re.compile(r"https?://[^/?#]+", re.IGNORECASE)


class StepKind(StrEnum):
    LEARN = "learn"
    PRACTICE = "practice"
    CHECK = "check"


@dataclass(frozen=True, slots=True)
class Resource:
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class NewStep:
    kind: StepKind
    title: str
    minutes: int
    details: str = ""
    resources: tuple[Resource, ...] = ()

    @classmethod
    def parse(
        cls,
        *,
        kind: str,
        title: str,
        minutes: int,
        details: str,
        resources: Sequence[tuple[str, str]],
    ) -> Self:
        try:
            step_kind = StepKind(kind.strip().lower())
        except ValueError:
            allowed = ", ".join(member.value for member in StepKind)
            raise InvalidValue(
                "kind", f"kind {kind!r} — допустимо {allowed}."
            ) from None
        title = one_line(title)
        if not title or len(title) > MAX_STEP_TITLE_LENGTH:
            raise InvalidValue(
                "title", f"назва — від 1 до {MAX_STEP_TITLE_LENGTH} символів."
            )
        if not 1 <= minutes <= MAX_STEP_MINUTES:
            raise InvalidValue("minutes", f"minutes — від 1 до {MAX_STEP_MINUTES}.")
        details = details.strip()
        if len(details) > MAX_STEP_DETAILS_LENGTH:
            raise InvalidValue(
                "details", f"details — до {MAX_STEP_DETAILS_LENGTH} символів."
            )
        if len(resources) > MAX_RESOURCES:
            raise InvalidValue("resources", f"до {MAX_RESOURCES} ресурсів.")
        return cls(
            step_kind,
            title,
            minutes,
            details,
            tuple(_resource(*resource) for resource in resources),
        )


@dataclass(frozen=True, slots=True)
class PrepStep:
    """Збережений крок. `number` — номер у межах користувача, `id` — внутрішній ключ,
    `position` — порядок у плані теми."""

    id: StepId
    number: int
    position: int
    kind: StepKind
    title: str
    minutes: int
    details: str
    resources: tuple[Resource, ...]
    done_at: datetime | None = None
    note: str = ""


def check_plan(kept: Sequence[PrepStep], new: Sequence[NewStep]) -> None:
    """План = виконані кроки, що лишаються, + нові; межі рахуються для всього плану."""
    total = len(kept) + len(new)
    if not MIN_STEPS <= total <= MAX_STEPS:
        raise InvalidValue(
            "steps",
            f"У плані {total} кроків (разом із виконаними {len(kept)}) — "
            f"треба від {MIN_STEPS} до {MAX_STEPS}.",
        )
    kinds = {step.kind for step in kept} | {step.kind for step in new}
    for kind in (StepKind.PRACTICE, StepKind.CHECK):
        if kind not in kinds:
            raise InvalidValue("steps", f"У плані немає жодного кроку {kind.value}.")


def parse_note(note: str) -> str:
    note = note.strip()
    if len(note) > MAX_NOTE_LENGTH:
        raise InvalidValue("note", f"Нотатка — до {MAX_NOTE_LENGTH} символів.")
    return note


def _resource(title: str, url: str) -> Resource:
    title = one_line(title)
    if not title or len(title) > MAX_RESOURCE_TITLE_LENGTH:
        raise InvalidValue(
            "resources",
            f"назва ресурсу — від 1 до {MAX_RESOURCE_TITLE_LENGTH} символів.",
        )
    url = url.strip()
    if (
        len(url) > MAX_URL_LENGTH
        or WEB_LINK.match(url) is None
        or any(char.isspace() for char in url)
    ):
        raise InvalidValue("resources", f"ресурс {url!r} — лише посилання http(s)://.")
    return Resource(title, url)
