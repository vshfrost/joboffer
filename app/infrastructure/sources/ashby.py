"""Ashby: публічний posting API (`api.ashbyhq.com/posting-api/job-board/<slug>`), без ключа."""

from urllib.parse import quote

from domain.profile.modes import WorkMode
from domain.shared.text import html_to_text
from domain.sources.failure import FailureReason, SourceError
from domain.sources.labels import parse_work_mode_label
from domain.sources.posting import Posting, sanitize
from domain.sources.target import SourceTarget
from infrastructure.sources.http import Fetcher, as_dict, as_list, as_str

API_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


class AshbySource:
    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def fetch(self, target: SourceTarget) -> list[Posting]:
        data = await self._fetcher.get_json(
            API_URL.format(slug=quote(target.ref, safe=""))
        )
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise SourceError(FailureReason.INVALID)
        postings = (_posting(as_dict(job)) for job in as_list(data["jobs"]))
        return [posting for posting in postings if posting is not None]


def _posting(job: dict[str, object]) -> Posting | None:
    if job.get("isListed") is False:
        return None
    secondary = [as_dict(place) for place in as_list(job.get("secondaryLocations"))]
    return sanitize(
        Posting(
            title=as_str(job.get("title")),
            url=as_str(job.get("jobUrl")),
            text=as_str(job.get("descriptionPlain"))
            or html_to_text(as_str(job.get("descriptionHtml"))),
            locations=(
                as_str(job.get("location")),
                *(as_str(place.get("location")) for place in secondary),
            ),
            countries=(_country(job), *(_country(place) for place in secondary)),
            work_mode=_mode(job),
        )
    )


def _country(place: dict[str, object]) -> str:
    address = as_dict(as_dict(place.get("address")).get("postalAddress"))
    return as_str(address.get("addressCountry"))


def _mode(job: dict[str, object]) -> WorkMode | None:
    # workplaceType точніший за isRemote («Hybrid» часто йде з isRemote=true).
    mode = parse_work_mode_label(as_str(job.get("workplaceType")))
    if mode is None and job.get("isRemote") is True:
        return WorkMode.REMOTE
    return mode
