"""Пробний запит слагу: найлегший запит платформи з коротким таймаутом."""

import httpx2
import pytest
from anyio.from_thread import BlockingPortal

from domain.sources.failure import FailureReason, SourceError
from domain.sources.kinds import Platform
from infrastructure.sources import http
from infrastructure.sources.probe import PROBE_TIMEOUT, AtsProbe
from tests.support.sources_net import Scripted, ok


def probe(script: Scripted) -> AtsProbe:
    return AtsProbe(httpx2.MockTransport(script))


@pytest.mark.parametrize(
    ("platform", "host", "path", "query"),
    [
        (Platform.GREENHOUSE, "boards-api.greenhouse.io", "/v1/boards/acme", ""),
        (Platform.ASHBY, "api.ashbyhq.com", "/posting-api/job-board/acme", ""),
        (Platform.LEVER, "api.lever.co", "/v0/postings/acme", "mode=json&limit=1"),
    ],
)
def test_probe_makes_one_light_request_with_a_short_timeout(
    portal: BlockingPortal, platform: Platform, host: str, path: str, query: str
) -> None:
    script = Scripted(ok())

    portal.call(probe(script).check, platform, "acme")

    (request,) = script.requests
    assert (request.url.host, request.url.path, request.url.query.decode()) == (
        host,
        path,
        query,
    )
    assert request.extensions["timeout"]["read"] == PROBE_TIMEOUT
    assert PROBE_TIMEOUT <= 10
    assert request.headers["User-Agent"] == http.USER_AGENT


@pytest.mark.parametrize("platform", list(Platform))
def test_unknown_company_is_not_found_without_retry(
    portal: BlockingPortal, platform: Platform
) -> None:
    script = Scripted(httpx2.Response(404))

    with pytest.raises(SourceError) as error:
        portal.call(probe(script).check, platform, "nope")

    assert error.value.reason is FailureReason.NOT_FOUND
    assert len(script.requests) == 1


def test_timeout_is_retried_once_then_reported(portal: BlockingPortal) -> None:
    script = Scripted(httpx2.ReadTimeout("slow"))

    with pytest.raises(SourceError) as error:
        portal.call(probe(script).check, Platform.ASHBY, "acme")

    assert error.value.reason is FailureReason.TIMEOUT
    assert len(script.requests) == 2


def test_slug_is_escaped_in_the_url(portal: BlockingPortal) -> None:
    script = Scripted(ok())

    portal.call(probe(script).check, Platform.LEVER, "a/b?c")

    (request,) = script.requests
    assert request.url.raw_path.startswith(b"/v0/postings/a%2Fb%3Fc?")
