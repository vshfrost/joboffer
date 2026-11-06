"""Порти читання джерел вакансій: лише мережа, у базу не пишуть."""

from typing import Protocol

from domain.sources.kinds import Platform
from domain.sources.posting import Posting
from domain.sources.target import SourceTarget


class JobSource(Protocol):
    """Джерело вакансій: ATS-компанії й RSS-стрічки за одним портом. Збій — `SourceError`;
    вміст відповіді — недовірені дані."""

    async def fetch(self, target: SourceTarget) -> list[Posting]:
        """Усі актуальні вакансії цілі, очищені `sanitize` (текст без HTML, канонічний URL)."""
        ...


class CompanyProbe(Protocol):
    """Пробний запит до ATS: чи є в компанії сторінка вакансій зі слагом. `SourceError` —
    нема (`NOT_FOUND`) чи не вдалось перевірити."""

    async def check(self, platform: Platform, slug: str) -> None: ...
