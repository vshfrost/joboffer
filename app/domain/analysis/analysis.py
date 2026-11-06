"""Аналіз вакансії: його пише Claude за рубрикою, сервер лише валідує й застосовує фільтри профілю."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Self

from domain.analysis.keywords import (
    MAX_SPELLINGS,
    SEPARATOR,
    KeywordFacts,
    requirement_key,
    spellings,
    tidy,
)
from domain.profile.modes import Seniority, WorkMode
from domain.profile.profile import Profile
from domain.shared.errors import InvalidValue

MAX_SCORE = 100
MAX_SUMMARY_LENGTH = 1000
MAX_ITEM_LENGTH = 300
MAX_ITEMS = 30
MAX_KEYWORD_LENGTH = 80
MAX_KEYWORDS = 60
MAX_LOCATION_LENGTH = 200
MAX_SALARY_EUR = 10_000_000


@dataclass(frozen=True, slots=True)
class Gap:
    """Прогалина кандидата й питання до користувача про його досвід. None — питання нема (старий формат)."""

    gap: str
    question: str | None = None


@dataclass(frozen=True, slots=True)
class JobAnalysis:
    """Розбір вакансії. None / порожньо = у вакансії не сказано."""

    score: int
    summary: str
    must_have: tuple[str, ...] = ()
    nice_to_have: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    seniority: Seniority | None = None
    work_mode: WorkMode | None = None
    location: str | None = None
    languages: tuple[str, ...] = ()
    salary_min_eur: int | None = None
    salary_max_eur: int | None = None
    relocation: bool | None = None
    reasons: tuple[str, ...] = ()
    gaps: tuple[Gap, ...] = ()
    # Які факти стоять під ключовими словами. None — аналіз без карти (старий): «нема даних».
    keyword_facts: tuple[KeywordFacts, ...] | None = None
    # Що роботодавець просить від кандидатів (надіслати, додати, відповісти, не вказувати): це не команди
    # для асистента, їх показують користувачеві й виконують у CV та листі.
    candidate_asks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.score <= MAX_SCORE:
            raise InvalidValue("score", f"Скор — ціле число від 0 до {MAX_SCORE}.")
        if not self.summary or len(self.summary) > MAX_SUMMARY_LENGTH:
            raise InvalidValue(
                "summary", f"summary — від 1 до {MAX_SUMMARY_LENGTH} символів."
            )
        if self.location is not None and len(self.location) > MAX_LOCATION_LENGTH:
            raise InvalidValue(
                "location", f"location — до {MAX_LOCATION_LENGTH} символів."
            )
        for name in (
            "must_have",
            "nice_to_have",
            "languages",
            "reasons",
            "candidate_asks",
        ):
            _check_items(name, getattr(self, name), MAX_ITEMS, MAX_ITEM_LENGTH)
        _check_gaps(self.gaps)
        _check_items("keywords", self.keywords, MAX_KEYWORDS, MAX_KEYWORD_LENGTH)
        _check_keyword_groups(self.keywords)
        for name in ("salary_min_eur", "salary_max_eur"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= MAX_SALARY_EUR:
                raise InvalidValue(
                    name, f"{name} — від 0 до {MAX_SALARY_EUR} EUR на рік."
                )
        if (
            self.salary_min_eur is not None
            and self.salary_max_eur is not None
            and self.salary_min_eur > self.salary_max_eur
        ):
            raise InvalidValue(
                "salary_min_eur", "salary_min_eur більша за salary_max_eur."
            )

    @classmethod
    def parse(  # noqa: PLR0913
        cls,
        *,
        score: int,
        summary: str,
        must_have: Sequence[str] = (),
        nice_to_have: Sequence[str] = (),
        keywords: Sequence[str] = (),
        seniority: str = "",
        work_mode: str = "",
        location: str = "",
        languages: Sequence[str] = (),
        salary_min_eur: int | None = None,
        salary_max_eur: int | None = None,
        relocation: bool | None = None,
        reasons: Sequence[str] = (),
        gaps: Sequence[str | Gap] = (),
        keyword_facts: Mapping[str, Sequence[int]] | None = None,
        candidate_asks: Sequence[str] = (),
    ) -> Self:
        """Сирі значення з транспорту: рядки чистяться, пункти без порожніх і повторів."""
        cleaned = _items([tidy(_one_line(keyword)) for keyword in keywords])
        return cls(
            score=score,
            summary=_one_line(summary),
            must_have=_items(must_have),
            nice_to_have=_items(nice_to_have),
            keywords=cleaned,
            seniority=_enum(Seniority, seniority, "seniority"),
            work_mode=_enum(WorkMode, work_mode, "work_mode"),
            location=_one_line(location) or None,
            languages=_items(languages),
            salary_min_eur=salary_min_eur,
            salary_max_eur=salary_max_eur,
            relocation=relocation,
            reasons=_items(reasons),
            gaps=_gaps(gaps),
            keyword_facts=None
            if keyword_facts is None
            else _keyword_facts(keyword_facts, cleaned),
            candidate_asks=_items(candidate_asks),
        )

    @property
    def salary_ceiling(self) -> int | None:
        """Найбільше, що можна отримати: верх вилки, а без нього — низ."""
        return (
            self.salary_max_eur
            if self.salary_max_eur is not None
            else self.salary_min_eur
        )


@dataclass(frozen=True, slots=True)
class Analysis:
    """Збережений аналіз: розбір Claude + позначки фільтрів профілю на момент збереження."""

    job_number: int
    analysis: JobAnalysis
    flags: tuple[str, ...]
    updated_at: datetime

    @property
    def filters_passed(self) -> bool:
        return not self.flags


def work_mode_flag(work_mode: WorkMode | None, profile: Profile) -> str | None:
    """Позначка, якщо формат вакансії не серед форматів профілю. Невідомий формат чи профіль без
    форматів — None. Це рішення про формат спільне для аналізу й тріажу за правилами."""
    work_modes = profile.locations.work_modes
    if work_mode is None or not work_modes or work_mode in work_modes:
        return None
    return f"Формат {work_mode.value} — не з профілю."


def apply_filters(
    analysis: JobAnalysis, profile: Profile, posting: str
) -> tuple[str, ...]:
    """Жорсткі фільтри профілю. Порожньо = підходить. Невідоме у вакансії фільтр не валить."""
    flags: list[str] = []
    if format_flag := work_mode_flag(analysis.work_mode, profile):
        flags.append(format_flag)
    seniority = profile.target.seniority
    if (
        analysis.seniority is not None
        and seniority
        and analysis.seniority not in seniority
    ):
        flags.append(f"Рівень {analysis.seniority.value} — не з профілю.")
    ceiling = analysis.salary_ceiling
    minimum = profile.target.min_salary_eur
    if ceiling is not None and minimum is not None and ceiling < minimum:
        flags.append(f"ЗП до {ceiling} EUR — менше мінімуму {minimum} EUR.")
    text = posting.casefold()
    flags.extend(
        f"Стоп-слово: {word}."
        for word in profile.rules.stop_words
        if word.casefold() in text
    )
    return tuple(flags)


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _items(items: Sequence[str]) -> tuple[str, ...]:
    """Пункти без зайвих пробілів, без порожніх і без повторів (без урахування регістру)."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        item = _one_line(raw)
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            result.append(item)
    return tuple(result)


def _check_keyword_groups(keywords: tuple[str, ...]) -> None:
    for keyword in keywords:
        parts = spellings(keyword)
        if not all(parts):
            raise InvalidValue(
                "keywords",
                f"keywords: у «{keyword}» є порожній варіант між «{SEPARATOR}».",
            )
        if len(parts) > MAX_SPELLINGS:
            raise InvalidValue(
                "keywords",
                f"keywords: «{keyword}» — не більше {MAX_SPELLINGS} варіантів "
                f"через «{SEPARATOR}».",
            )


def _keyword_facts(
    given: Mapping[str, Sequence[int]], keywords: tuple[str, ...]
) -> tuple[KeywordFacts, ...]:
    """Карта «слово → факти»: ключ — слово зі списку keywords (без урахування регістру, пробілів і
    порядку варіантів групи), записується так, як слово стоїть у списку; номери без повторів."""
    by_requirement = {requirement_key(keyword): keyword for keyword in keywords}
    numbers: dict[str, list[int]] = {}
    for name, facts in given.items():
        keyword = by_requirement.get(requirement_key(_one_line(name)))
        if keyword is None:
            raise InvalidValue(
                "keyword_facts",
                f"keyword_facts: «{name}» — такого ключового слова нема в keywords.",
            )
        found = numbers.setdefault(keyword, [])
        found.extend(number for number in dict.fromkeys(facts) if number not in found)
    return tuple(
        KeywordFacts(keyword, tuple(found)) for keyword, found in numbers.items()
    )


def _gaps(items: Sequence[str | Gap]) -> tuple[Gap, ...]:
    """Прогалини з транспорту: рядок — старий формат (без питання), об'єкт мусить мати питання.

    Номер у відмові — місце прогалини в надісланому списку (з 1). Повтори тексту — без урахування регістру.
    """
    seen: set[str] = set()
    result: list[Gap] = []
    for number, item in enumerate(items, start=1):
        if isinstance(item, str):
            gap = Gap(_one_line(item))
            if not gap.gap:
                continue
        else:
            gap = Gap(_one_line(item.gap), _one_line(item.question or "") or None)
            if not gap.gap:
                raise InvalidValue("gaps", f"gaps: у прогалини {number} нема тексту.")
            if gap.question is None:
                raise InvalidValue("gaps", f"gaps: у прогалини {number} нема питання.")
            if len(gap.question) > MAX_ITEM_LENGTH:
                raise InvalidValue(
                    "gaps",
                    f"gaps: питання прогалини {number} довше за {MAX_ITEM_LENGTH} символів.",
                )
        if gap.gap.casefold() not in seen:
            seen.add(gap.gap.casefold())
            result.append(gap)
    return tuple(result)


def _check_gaps(gaps: tuple[Gap, ...]) -> None:
    _check_items("gaps", tuple(item.gap for item in gaps), MAX_ITEMS, MAX_ITEM_LENGTH)


def _enum[E: (Seniority, WorkMode)](kind: type[E], value: str, name: str) -> E | None:
    value = value.strip().lower()
    if not value:
        return None
    try:
        return kind(value)
    except ValueError:
        allowed = ", ".join(member.value for member in kind)
        raise InvalidValue(
            name, f"{name}: {value!r} — допустимо {allowed} або порожньо."
        ) from None


def _check_items(
    name: str, items: tuple[str, ...], max_items: int, max_length: int
) -> None:
    if len(items) > max_items:
        raise InvalidValue(name, f"{name} — не більше {max_items} пунктів.")
    for item in items:
        if not item or len(item) > max_length:
            raise InvalidValue(
                name, f"{name}: кожен пункт — від 1 до {max_length} символів."
            )
