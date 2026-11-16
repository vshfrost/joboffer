"""SmartRecruiters: публічний postings API (`api.smartrecruiters.com/v1/companies/<slug>/postings`),
без ключа. Список віддає лише назви й місця, опис — окремий запит на кожну вакансію, тож деталі
беремо лише для тих, що пройшли попередній фільтр профілю (`keep`). Неіснуюча компанія — теж 200,
але з `totalFound: 0`; порожньо = «компанію не знайдено»."""

from dataclasses import replace
from urllib.parse import quote

from application.ports.job_sources import Keep
from domain.profile.modes import WorkMode
from domain.shared.text import html_to_text
from domain.sources.failure import FailureReason, SourceError
from domain.sources.posting import Posting, sanitize
from domain.sources.target import SourceTarget
from infrastructure.sources.http import Fetcher, as_dict, as_list, as_str

LIST_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
DETAIL_URL = LIST_URL + "/{posting_id}"
PAGE_SIZE = 100
POSTING_URL = "https://jobs.smartrecruiters.com/{slug}/{posting_id}"
# Порядок розділів опису в оголошенні.
SECTIONS = (
    "companyDescription",
    "jobDescription",
    "qualifications",
    "additionalInformation",
)


class SmartRecruitersSource:
    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def fetch(
        self, target: SourceTarget, keep: Keep | None = None
    ) -> list[Posting]:
        slug = quote(target.ref, safe="")
        listed = await self._listing(slug)
        wanted = [
            (job_id, stub) for job_id, stub in listed if keep is None or keep(stub)
        ]
        details = [
            await self._with_details(slug, job_id, stub) for job_id, stub in wanted
        ]
        return [posting for posting in details if posting is not None]

    async def _listing(self, slug: str) -> list[tuple[str, Posting]]:
        """Вакансії зі списку (id і вакансія без тексту) з усіх сторінок."""
        found: list[tuple[str, Posting]] = []
        offset = 0
        while True:
            data = await self._fetcher.get_json(
                LIST_URL.format(slug=slug),
                {"limit": str(PAGE_SIZE), "offset": str(offset)},
            )
            if not isinstance(data, dict) or not isinstance(data.get("content"), list):
                raise SourceError(FailureReason.INVALID)
            total = data.get("totalFound")
            if not isinstance(total, int):
                raise SourceError(FailureReason.INVALID)
            if offset == 0 and total == 0:
                raise SourceError(FailureReason.NOT_FOUND)
            page = as_list(data["content"])
            found += [
                item for item in (_stub(as_dict(job), slug) for job in page) if item
            ]
            offset += len(page)
            if not page or offset >= total:
                return found

    async def _with_details(
        self, slug: str, job_id: str, stub: Posting
    ) -> Posting | None:
        detail = as_dict(
            await self._fetcher.get_json(
                DETAIL_URL.format(slug=slug, posting_id=job_id)
            )
        )
        return sanitize(
            replace(
                stub,
                url=as_str(detail.get("postingUrl")) or stub.url,
                text=_description(detail),
            )
        )


def _stub(job: dict[str, object], slug: str) -> tuple[str, Posting] | None:
    job_id = as_str(job.get("id"))
    location = as_dict(job.get("location"))
    stub = sanitize(
        Posting(
            title=as_str(job.get("name")),
            url=POSTING_URL.format(slug=slug, posting_id=quote(job_id, safe="")),
            text="",
            locations=(
                as_str(location.get("fullLocation")) or as_str(location.get("city")),
            ),
            countries=(as_str(location.get("country")).upper(),),
            work_mode=_mode(location),
        )
    )
    return (job_id, stub) if job_id and stub is not None else None


def _mode(location: dict[str, object]) -> WorkMode | None:
    if location.get("remote") is True:
        return WorkMode.REMOTE
    return WorkMode.HYBRID if location.get("hybrid") is True else None


def _description(detail: dict[str, object]) -> str:
    """Розділи оголошення в порядку сторінки: «Назва розділу» і текст без HTML."""
    sections = as_dict(as_dict(detail.get("jobAd")).get("sections"))
    parts = []
    for key in SECTIONS:
        section = as_dict(sections.get(key))
        text = html_to_text(as_str(section.get("text")))
        if text:
            parts.append(f"{as_str(section.get('title'))}\n{text}".strip())
    return "\n\n".join(parts)
