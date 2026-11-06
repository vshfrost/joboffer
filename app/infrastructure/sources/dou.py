"""DOU: офіційний RSS вакансій (`jobs.dou.ua/vacancies/feeds/`), повні описи, 25 останніх. Назва
вакансії — «Посада в Компанія, місто, віддалено»; країни в RSS нема, DOU — український ринок."""

from domain.sources.posting import Posting
from domain.sources.target import SourceTarget
from infrastructure.sources.http import Fetcher
from infrastructure.sources.rss import BASE_URLS, feed_postings


class DouSource:
    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def fetch(self, target: SourceTarget) -> list[Posting]:
        body = await self._fetcher.get_bytes(f"{BASE_URLS['dou']}?{target.ref}")
        return feed_postings(body, countries=("Ukraine",))
