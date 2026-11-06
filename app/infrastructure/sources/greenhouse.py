"""Greenhouse: публічний job board API (`boards-api.greenhouse.io`), без ключа."""

import html
from urllib.parse import quote

from domain.shared.text import html_to_text
from domain.sources.failure import FailureReason, SourceError
from domain.sources.posting import Posting, sanitize
from domain.sources.target import SourceTarget
from infrastructure.sources.http import Fetcher, as_dict, as_list, as_str

API_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


class GreenhouseSource:
    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def fetch(self, target: SourceTarget) -> list[Posting]:
        data = await self._fetcher.get_json(
            API_URL.format(slug=quote(target.ref, safe="")), {"content": "true"}
        )
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise SourceError(FailureReason.INVALID)
        postings = (_posting(as_dict(job)) for job in as_list(data["jobs"]))
        return [posting for posting in postings if posting is not None]


def _posting(job: dict[str, object]) -> Posting | None:
    return sanitize(
        Posting(
            title=as_str(job.get("title")),
            url=as_str(job.get("absolute_url")),
            text=_description(as_str(job.get("content"))),
            locations=(as_str(as_dict(job.get("location")).get("name")),),
        )
    )


def _description(content: str) -> str:
    # Greenhouse віддає HTML екранованим («&lt;p&gt;»): спершу розекранувати.
    if "<" not in content:
        content = html.unescape(content)
    return html_to_text(content)
