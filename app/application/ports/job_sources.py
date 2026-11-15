"""Порти читання джерел вакансій: лише мережа, у базу не пишуть."""

from collections.abc import Callable
from typing import Protocol

from domain.sources.kinds import Platform
from domain.sources.posting import Posting
from domain.sources.target import SourceTarget

# Попередній фільтр за вакансією зі списку (назва, місце, формат; без тексту): True — вакансія
# може пройти фільтр профілю, тож варто вантажити її повний опис.
type Keep = Callable[[Posting], bool]


class JobSource(Protocol):
    """Джерело вакансій: ATS-компанії й RSS-стрічки за одним портом. Збій — `SourceError`;
    вміст відповіді — недовірені дані."""

    async def fetch(
        self, target: SourceTarget, keep: Keep | None = None
    ) -> list[Posting]:
        """Усі актуальні вакансії цілі, очищені `sanitize` (текст без HTML, канонічний URL).
        `keep` — необов'язковий попередній фільтр: адаптер, якому текст дорого вантажити окремим
        запитом (SmartRecruiters), бере його лише для вакансій, що пройшли `keep`; решта адаптерів
        його ігнорують."""
        ...


class CompanyProbe(Protocol):
    """Пробний запит до ATS: чи є в компанії сторінка вакансій зі слагом. `SourceError` —
    нема (`NOT_FOUND`) чи не вдалось перевірити."""

    async def check(self, platform: Platform, slug: str) -> None: ...
