"""HTTP-доступ до джерел: статуси → коди збоїв, один повтор, ліміт розміру, User-Agent."""

import json

import httpx2
import pytest
from anyio.from_thread import BlockingPortal

from domain.sources.failure import FailureReason, SourceError
from infrastructure.sources import http
from infrastructure.sources.http import as_dict, as_list, as_str, new_client
from tests.support.sources_net import PAUSE, Scripted, ok

URL = "https://boards.example.com/api"


def test_get_returns_body_and_sends_params_and_timeout(portal: BlockingPortal) -> None:
    script = Scripted(ok(b"hello"))

    body = portal.call(script.fetcher().get_bytes, URL, {"content": "true"}, 12.0)

    assert body == b"hello"
    (request,) = script.requests
    assert request.url.params["content"] == "true"
    assert request.extensions["timeout"]["read"] == 12.0
    assert script.pauses == []


def test_requests_carry_own_user_agent(portal: BlockingPortal) -> None:
    script = Scripted(ok())
    fetcher = http.Fetcher(new_client(httpx2.MockTransport(script)))

    portal.call(fetcher.get_bytes, URL)

    (request,) = script.requests
    assert request.headers["User-Agent"] == http.USER_AGENT
    assert "joboffer" in http.USER_AGENT


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirect_is_not_followed(portal: BlockingPortal, status: int) -> None:
    script = Scripted(
        httpx2.Response(status, headers={"Location": "http://169.254.169.254/"})
    )
    fetcher = http.Fetcher(new_client(httpx2.MockTransport(script)))

    with pytest.raises(SourceError) as error:
        portal.call(fetcher.get_bytes, URL)

    assert error.value.reason is FailureReason.REJECTED
    assert [str(request.url) for request in script.requests] == [URL]


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (404, FailureReason.NOT_FOUND),
        (403, FailureReason.REJECTED),
        (400, FailureReason.REJECTED),
        (410, FailureReason.REJECTED),
    ],
)
def test_client_errors_are_not_retried(
    portal: BlockingPortal, status: int, reason: FailureReason
) -> None:
    script = Scripted(httpx2.Response(status))

    with pytest.raises(SourceError) as error:
        portal.call(script.fetcher().get_bytes, URL)

    assert error.value.reason is reason
    assert len(script.requests) == 1
    assert script.pauses == []


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (httpx2.Response(429), FailureReason.RATE_LIMITED),
        (httpx2.Response(500), FailureReason.UNAVAILABLE),
        (httpx2.Response(503), FailureReason.UNAVAILABLE),
        (httpx2.ReadTimeout("slow"), FailureReason.TIMEOUT),
        (httpx2.ConnectTimeout("slow"), FailureReason.TIMEOUT),
        (httpx2.ConnectError("down"), FailureReason.UNAVAILABLE),
        (httpx2.RemoteProtocolError("dropped"), FailureReason.UNAVAILABLE),
    ],
)
def test_temporary_failure_is_retried_once_after_a_pause(
    portal: BlockingPortal, failure: httpx2.Response | Exception, reason: FailureReason
) -> None:
    recovered = Scripted(failure, ok(b"fine"))
    assert portal.call(recovered.fetcher().get_bytes, URL) == b"fine"
    assert recovered.pauses == [PAUSE]
    assert len(recovered.requests) == 2

    failing = Scripted(failure)
    with pytest.raises(SourceError) as error:
        portal.call(failing.fetcher().get_bytes, URL)
    assert error.value.reason is reason
    assert len(failing.requests) == 2
    assert failing.pauses == [PAUSE]


def test_body_over_30_megabytes_is_invalid(
    portal: BlockingPortal, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert http.MAX_BODY_BYTES == 30_000_000
    monkeypatch.setattr(http, "MAX_BODY_BYTES", 10)
    script = Scripted(ok(b"x" * 11))

    with pytest.raises(SourceError) as error:
        portal.call(script.fetcher().get_bytes, URL)

    assert error.value.reason is FailureReason.INVALID
    assert len(script.requests) == 1
    assert script.pauses == []


def test_body_at_the_limit_is_accepted(
    portal: BlockingPortal, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "MAX_BODY_BYTES", 10)

    assert portal.call(Scripted(ok(b"x" * 10)).fetcher().get_bytes, URL) == b"x" * 10


def test_get_json_parses(portal: BlockingPortal) -> None:
    payload = {"jobs": [1, 2]}

    data = portal.call(
        Scripted(ok(json.dumps(payload).encode())).fetcher().get_json, URL
    )

    assert data == payload


@pytest.mark.parametrize("garbage", [b"<html>", b"", b"\xff\xfe"])
def test_get_json_rejects_non_json_as_invalid(
    portal: BlockingPortal, garbage: bytes
) -> None:
    script = Scripted(ok(garbage))

    with pytest.raises(SourceError) as error:
        portal.call(script.fetcher().get_json, URL)

    assert error.value.reason is FailureReason.INVALID
    assert len(script.requests) == 1


def test_json_helpers_tolerate_wrong_types() -> None:
    assert as_dict({"a": 1}) == {"a": 1}
    assert as_dict([1]) == {}
    assert as_dict(None) == {}
    assert as_list([1]) == [1]
    assert as_list({"a": 1}) == []
    assert as_str("x") == "x"
    assert as_str(5) == ""
    assert as_str(None) == ""
