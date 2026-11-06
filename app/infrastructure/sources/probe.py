"""Пробний запит при додаванні компанії: чи є в неї сторінка вакансій зі слагом. Єдине місце,
де веб ходить у мережу ATS — один легкий запит із коротким таймаутом."""

from urllib.parse import quote

import httpx2

from domain.sources.kinds import Platform
from infrastructure.sources.http import Fetcher, new_client

PROBE_TIMEOUT = 8.0
# Найлегший запит платформи: Greenhouse віддає опис дошки, Lever — одну вакансію, Ashby лише
# повну дошку (окремого легкого ендпоінта нема).
PROBE_URLS: dict[Platform, tuple[str, dict[str, str]]] = {
    Platform.GREENHOUSE: ("https://boards-api.greenhouse.io/v1/boards/{slug}", {}),
    Platform.ASHBY: ("https://api.ashbyhq.com/posting-api/job-board/{slug}", {}),
    Platform.LEVER: (
        "https://api.lever.co/v0/postings/{slug}",
        {"mode": "json", "limit": "1"},
    ),
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
            await Fetcher(client, pause=RETRY_PAUSE).get_bytes(
                url.format(slug=quote(slug, safe="")), params, PROBE_TIMEOUT
            )
