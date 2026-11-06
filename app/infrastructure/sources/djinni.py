"""Djinni: RSS вакансій (`djinni.co/jobs/rss/`), до 100 останніх, описи ~3K. Локації в RSS нема
(`remote_type` ігнорується), компанія — лише якщо вона є в назві («… у Brightloop»). Недокументований
JSON `djinni.co/api/jobs/` не використовується."""

from domain.sources.posting import Posting
from domain.sources.target import SourceTarget
from infrastructure.sources.http import Fetcher
from infrastructure.sources.rss import BASE_URLS, feed_postings


class DjinniSource:
    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def fetch(self, target: SourceTarget) -> list[Posting]:
        body = await self._fetcher.get_bytes(f"{BASE_URLS['djinni']}?{target.ref}")
        return feed_postings(body)
