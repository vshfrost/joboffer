"""Lever: публічний postings API (`api.lever.co/v0/postings/<slug>`), без ключа. Віддає повні
описи, тож повільний — таймаут більший."""

from urllib.parse import quote

from domain.shared.text import html_to_text
from domain.sources.failure import FailureReason, SourceError
from domain.sources.labels import parse_work_mode_label
from domain.sources.posting import Posting, sanitize
from domain.sources.target import SourceTarget
from infrastructure.sources.http import Fetcher, as_dict, as_list, as_str

API_URL = "https://api.lever.co/v0/postings/{slug}"
TIMEOUT = 90.0


class LeverSource:
    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def fetch(self, target: SourceTarget) -> list[Posting]:
        data = await self._fetcher.get_json(
            API_URL.format(slug=quote(target.ref, safe="")),
            {"mode": "json"},
            timeout_seconds=TIMEOUT,
        )
        if not isinstance(data, list):
            raise SourceError(FailureReason.INVALID)
        postings = (_posting(as_dict(job)) for job in data)
        return [posting for posting in postings if posting is not None]


def _posting(job: dict[str, object]) -> Posting | None:
    # Поле `country` не беремо: це країна акаунта (вакансія «LATAM» має ES), не вакансії.
    categories = as_dict(job.get("categories"))
    return sanitize(
        Posting(
            title=as_str(job.get("text")),
            url=as_str(job.get("hostedUrl")),
            text=_description(job),
            locations=(
                as_str(categories.get("location")),
                *(as_str(place) for place in as_list(categories.get("allLocations"))),
            ),
            work_mode=parse_work_mode_label(as_str(job.get("workplaceType"))),
        )
    )


def _description(job: dict[str, object]) -> str:
    """Вступ і опис, далі списки (вимоги, умови) і заключна частина."""
    sections = [as_str(job.get("descriptionPlain"))]
    for item in as_list(job.get("lists")):
        section = as_dict(item)
        sections.append(
            f"{as_str(section.get('text'))}\n{html_to_text(as_str(section.get('content')))}"
        )
    sections.append(as_str(job.get("additionalPlain")))
    return "\n\n".join(part.strip() for part in sections if part.strip())
