"""Адреса клієнта для ліміту спроб: заголовок Cloudflare береться лише від довіреного локального проксі."""

from typing import Any, cast

import pytest
from starlette.requests import Request

from infrastructure.http.auth import CookieConfig, HttpAuth

COOKIE = CookieConfig(name="s", secure=True, max_age=60)


def auth(header: str | None = "cf-connecting-ip", trusted_proxies: int = 0) -> HttpAuth:
    return HttpAuth(cast(Any, None), COOKIE, trusted_proxies, client_ip_header=header)


def request(peer: str | None, **headers: str) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (peer, 1234) if peer else None,
        }
    )


@pytest.mark.parametrize("peer", ["127.0.0.1", "::1", "172.18.0.5", "10.0.0.2"])
def test_local_proxy_peer_is_trusted(peer: str) -> None:
    sent = request(peer, **{"CF-Connecting-IP": "203.0.113.9"})
    assert auth().client_key(sent) == "203.0.113.9"


def test_public_peer_cannot_forge_the_header() -> None:
    sent = request("93.184.216.34", **{"CF-Connecting-IP": "203.0.113.9"})
    assert auth().client_key(sent) == "93.184.216.34"


def test_without_configuration_the_header_is_ignored() -> None:
    sent = request("127.0.0.1", **{"CF-Connecting-IP": "203.0.113.9"})
    assert auth(header=None).client_key(sent) == "127.0.0.1"


def test_missing_header_falls_back_to_the_peer() -> None:
    assert auth().client_key(request("127.0.0.1")) == "127.0.0.1"


def test_garbage_header_value_falls_back_to_the_peer() -> None:
    sent = request("127.0.0.1", **{"CF-Connecting-IP": "not-an-ip"})
    assert auth().client_key(sent) == "127.0.0.1"


def test_ipv6_client_address_is_accepted() -> None:
    sent = request("127.0.0.1", **{"CF-Connecting-IP": "2001:db8::1"})
    assert auth().client_key(sent) == "2001:db8::1"


def test_configured_header_wins_over_forwarded_for() -> None:
    sent = request(
        "127.0.0.1",
        **{"CF-Connecting-IP": "203.0.113.9", "X-Forwarded-For": "1.1.1.1"},
    )
    assert auth(trusted_proxies=1).client_key(sent) == "203.0.113.9"


def test_forwarded_for_still_works_when_header_is_absent() -> None:
    sent = request("127.0.0.1", **{"X-Forwarded-For": "1.1.1.1"})
    assert auth(trusted_proxies=1).client_key(sent) == "1.1.1.1"


def test_unknown_peer_without_header() -> None:
    assert auth().client_key(request(None)) == "unknown"
