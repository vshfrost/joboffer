"""Вакансія з джерела після нормалізації: очищення недовірених полів."""

from collections.abc import Iterable
from dataclasses import dataclass, replace

from domain.jobs.job import MAX_TEXT_LENGTH
from domain.jobs.urls import normalize_url
from domain.profile.modes import WorkMode
from domain.shared.errors import InvalidValue
from domain.shared.text import is_invisible, one_line, tidy_lines

MAX_TITLE_LENGTH = 300
MAX_COMPANY_LENGTH = 200
MAX_LOCATION_LENGTH = 300


@dataclass(frozen=True, slots=True)
class Posting:
    """Вакансія з джерела: назва, канонічний URL, текст без HTML."""

    title: str
    url: str
    text: str
    # Компанія з самої вакансії (стрічки); None — береться з цілі джерела.
    company: str | None = None
    locations: tuple[str, ...] = ()
    # Країни зі структурованих полів джерела (повна назва, напр. «Spain»).
    countries: tuple[str, ...] = ()
    # Формат, якщо джерело його вказує; None — невідомо.
    work_mode: WorkMode | None = None
    # Джерело не має структурованої локації (RSS): місце профілю шукаємо ще й у тексті.
    locations_in_text: bool = False

    @property
    def location(self) -> str | None:
        """Локація для показу: поля джерела, інакше країни; None — джерело не дало."""
        return "; ".join(self.locations or self.countries)[:MAX_LOCATION_LENGTH] or None


def sanitize(raw: Posting) -> Posting | None:
    """Очищена вакансія: без невидимих символів, назва в один рядок, поля й текст у межах
    лімітів, URL канонічний. None — без назви чи придатного URL: брати нічого."""
    title = one_line(_visible(raw.title))[:MAX_TITLE_LENGTH]
    try:
        url = normalize_url(raw.url)
    except InvalidValue:
        return None
    if not title:
        return None
    company = one_line(_visible(raw.company or ""))[:MAX_COMPANY_LENGTH]
    return replace(
        raw,
        title=title,
        url=url,
        text=tidy_lines(_visible(raw.text).splitlines())[:MAX_TEXT_LENGTH],
        company=company or None,
        locations=_visible_all(raw.locations),
        countries=_visible_all(raw.countries),
    )


def _visible(text: str) -> str:
    """Без невидимих символів (NUL, керівні, zero-width, bidi); пробіли й переноси лишаються."""
    return "".join(char for char in text if not is_invisible(char))


def _visible_all(values: Iterable[str]) -> tuple[str, ...]:
    cleaned = (one_line(_visible(value)) for value in values)
    return tuple(dict.fromkeys(item for item in cleaned if item))
