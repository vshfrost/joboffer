"""SmartRecruiters: публічний postings API (stub)."""

from application.ports.job_sources import Keep
from domain.sources.posting import Posting
from domain.sources.target import SourceTarget
from infrastructure.sources.http import Fetcher


class SmartRecruitersSource:
    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def fetch(
        self, target: SourceTarget, keep: Keep | None = None
    ) -> list[Posting]:
        return []
