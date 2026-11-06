"""HTTP-доступ до джерел: свій User-Agent, таймаут, один повтор лише для тимчасових збоїв,
ліміт розміру відповіді. Усе, що повернулось, — недовірені дані; збій — `SourceError` з кодом."""

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping

import httpx2

from domain.sources.failure import FailureReason, SourceError

USER_AGENT = "joboffer/2.0 (personal job search; reads public job boards)"
DEFAULT_TIMEOUT = 20.0
MAX_BODY_BYTES = 30_000_000
RETRY_PAUSE = 5.0
# Один повтор — лише там, де збій може бути тимчасовим.
RETRYABLE = frozenset(
    {FailureReason.TIMEOUT, FailureReason.RATE_LIMITED, FailureReason.UNAVAILABLE}
)
HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR = 500


def new_client(
    transport: httpx2.AsyncBaseTransport | None = None,
) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        headers={"User-Agent": USER_AGENT}, follow_redirects=False, transport=transport
    )


class Fetcher:
    """GET з повтором. `sleep` і `pause` підміняються в тестах."""

    def __init__(
        self,
        client: httpx2.AsyncClient,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        pause: float = RETRY_PAUSE,
    ) -> None:
        self._client = client
        self._sleep = sleep
        self._pause = pause

    async def get_bytes(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT,
    ) -> bytes:
        try:
            return await self._get(url, params, timeout_seconds)
        except SourceError as exc:
            if exc.reason not in RETRYABLE:
                raise
        await self._sleep(self._pause)
        return await self._get(url, params, timeout_seconds)

    async def get_json(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT,
    ) -> object:
        body = await self.get_bytes(url, params, timeout_seconds)
        try:
            data: object = json.loads(body)
        except ValueError as exc:  # JSONDecodeError і UnicodeDecodeError
            raise SourceError(FailureReason.INVALID) from exc
        return data

    async def _get(
        self, url: str, params: Mapping[str, str] | None, timeout_seconds: float
    ) -> bytes:
        try:
            async with self._client.stream(
                "GET", url, params=params, timeout=timeout_seconds
            ) as response:
                _check_status(response.status_code)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BODY_BYTES:
                        raise SourceError(FailureReason.INVALID)
                return bytes(body)
        except httpx2.TimeoutException as exc:
            raise SourceError(FailureReason.TIMEOUT) from exc
        except httpx2.TransportError as exc:
            raise SourceError(FailureReason.UNAVAILABLE) from exc


def _check_status(status: int) -> None:
    if status == HTTP_OK:
        return
    if status == HTTP_NOT_FOUND:
        raise SourceError(FailureReason.NOT_FOUND)
    if status == HTTP_TOO_MANY_REQUESTS:
        raise SourceError(FailureReason.RATE_LIMITED)
    if status >= HTTP_SERVER_ERROR:
        raise SourceError(FailureReason.UNAVAILABLE)
    raise SourceError(FailureReason.REJECTED)


def as_dict(value: object) -> dict[str, object]:
    return {str(k): v for k, v in value.items()} if isinstance(value, dict) else {}


def as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def as_str(value: object) -> str:
    return value if isinstance(value, str) else ""
