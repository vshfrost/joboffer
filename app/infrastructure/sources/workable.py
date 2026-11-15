"""Workable: публічний widget API (`apply.workable.com/api/v1/widget/accounts/<slug>`), без ключа.
Один запит віддає всі вакансії з описами (`details=true`). «Сплячий» акаунт без вакансій — не
помилка. 429 — пауза й один повтор у `Fetcher`, далі `RATE_LIMITED` лише для цієї компанії."""

from urllib.parse import quote

from application.ports.job_sources import Keep
from domain.profile.modes import WorkMode
from domain.shared.text import html_to_text
from domain.sources.failure import FailureReason, SourceError
from domain.sources.posting import Posting, sanitize
from domain.sources.target import SourceTarget
from infrastructure.sources.http import Fetcher, as_dict, as_list, as_str

API_URL = "https://apply.workable.com/api/v1/widget/accounts/{slug}"


class WorkableSource:
    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def fetch(
        self, target: SourceTarget, keep: Keep | None = None
    ) -> list[Posting]:
        data = await self._fetcher.get_json(
            API_URL.format(slug=quote(target.ref, safe="")), {"details": "true"}
        )
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise SourceError(FailureReason.INVALID)
        postings = (_posting(as_dict(job)) for job in as_list(data["jobs"]))
        return [posting for posting in postings if posting is not None]


def _posting(job: dict[str, object]) -> Posting | None:
    places = [as_dict(place) for place in as_list(job.get("locations"))] or [job]
    return sanitize(
        Posting(
            title=as_str(job.get("title")),
            url=as_str(job.get("url")),
            text=html_to_text(as_str(job.get("description"))),
            locations=tuple(as_str(place.get("city")) for place in places),
            countries=tuple(as_str(place.get("country")) for place in places),
            work_mode=WorkMode.REMOTE if job.get("telecommuting") is True else None,
        )
    )
