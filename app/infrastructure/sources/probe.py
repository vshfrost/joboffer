"""Пробний запит при додаванні компанії: чи є в неї сторінка вакансій зі слагом. Єдине місце,
де веб ходить у мережу ATS — один легкий запит із коротким таймаутом."""

from urllib.parse import quote

import httpx2

from domain.sources.failure import FailureReason, SourceError
from domain.sources.kinds import Platform
from infrastructure.sources.http import Fetcher, new_client

PROBE_TIMEOUT = 8.0
# Найлегший запит платформи: Greenhouse віддає опис дошки, Lever — одну вакансію, Ashby лише
# повну дошку (окремого легкого ендпоінта нема), SmartRecruiters — одну вакансію зі списку, Workable —
# віджет акаунта (без деталей — без описів).
PROBE_URLS: dict[Platform, tuple[str, dict[str, str]]] = {
    Platform.GREENHOUSE: ("https://boards-api.greenhouse.io/v1/boards/{slug}", {}),
    Platform.ASHBY: ("https://api.ashbyhq.com/posting-api/job-board/{slug}", {}),
    Platform.LEVER: (
        "https://api.lever.co/v0/postings/{slug}",
        {"mode": "json", "limit": "1"},
    ),
    Platform.SMARTRECRUITERS: (
        "https://api.smartrecruiters.com/v1/companies/{slug}/postings",
        {"limit": "1"},
    ),
    Platform.WORKABLE: ("https://apply.workable.com/api/v1/widget/accounts/{slug}", {}),
}
# Користувач чекає на відповідь форми: повтор після збою — майже без паузи.
RETRY_PAUSE = 0.5


class AtsProbe:
    """`CompanyProbe` поверх публічних API. Клієнт створюється на кожну перевірку й
    закривається: компанії додають рідко."""

    def __init__(self, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def check(self, platform: Platform, slug: str) -> None:
        url, params = PROBE_URLS[platform]
        async with new_client(self._transport) as client:
            fetcher = Fetcher(client, pause=RETRY_PAUSE)
            address = url.format(slug=quote(slug, safe=""))
            if platform is not Platform.SMARTRECRUITERS:
                await fetcher.get_bytes(address, params, PROBE_TIMEOUT)
                return
            # SmartRecruiters на невідому компанію теж відповідає 200, лише з нулем вакансій.
            answer = await fetcher.get_json(address, params, PROBE_TIMEOUT)
            if isinstance(answer, dict) and answer.get("totalFound") == 0:
                raise SourceError(FailureReason.NOT_FOUND)
