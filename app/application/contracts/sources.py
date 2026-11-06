"""Вхідні дані керування джерелами: сирі значення форми з будь-якого транспорту."""

from dataclasses import dataclass
from datetime import datetime

from domain.sources.filtered import FilteredJob
from domain.sources.manage import CompanyRow, FeedRow


@dataclass(frozen=True, slots=True)
class CompanyInput:
    platform: str
    slug: str
    name: str = ""


@dataclass(frozen=True, slots=True)
class FeedInput:
    source: str
    query: str


@dataclass(frozen=True, slots=True)
class RefreshState:
    """«Оновити зараз» користувача: скільки запитів лишилось у вікні, коли звільниться наступний
    (None — запити є) і коли джерела востаннє оновлювались (None — прогонів ще не було)."""

    remaining: int
    next_at: datetime | None
    last_run_at: datetime | None


@dataclass(frozen=True, slots=True)
class SourcesOverview:
    """Джерела користувача зі станом прогонів, «оновити зараз» і вакансії, що вже не проходять фільтр."""

    companies: list[CompanyRow]
    feeds: list[FeedRow]
    refresh: RefreshState
    filtered: list[FilteredJob]
