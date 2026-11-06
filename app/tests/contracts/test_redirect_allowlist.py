"""Allowlist redirect_uri (адаптер на urllib): порівнюються розібрані частини, а не рядок."""

import pytest

from domain.oauth.redirect import CLAUDE_CALLBACK
from infrastructure.oauth.redirect import RedirectAllowlist

DEFAULT = RedirectAllowlist()
WILDCARD = RedirectAllowlist(("https://app.example/cb/*",))


@pytest.mark.parametrize(
    "uri",
    [
        CLAUDE_CALLBACK,
        "http://127.0.0.1:53123/callback",
        "http://localhost:8080/oauth/callback",
        "http://[::1]:9000/cb",
        "http://127.0.0.1/cb",
    ],
)
def test_default_allowlist_accepts_claude_and_loopback(uri: str) -> None:
    assert DEFAULT.allows(uri)


@pytest.mark.parametrize(
    "uri",
    [
        "https://evil.example/api/mcp/auth_callback",
        "https://claude.ai@evil.example/api/mcp/auth_callback",
        "https://claude.ai:evil@evil.example/api/mcp/auth_callback",
        "https://claude.ai:8443/api/mcp/auth_callback",
        "https://claude.ai/api/mcp/auth_callback?next=https://evil.example",
        "https://claude.ai/api/mcp/auth_callback#fragment",
        "https://claude.ai/api/mcp/auth_callback/",
        "http://claude.ai/api/mcp/auth_callback",
        "https://claude.ai/api/mcp/../auth_callback",
        "http://127.0.0.1.evil.example/cb",
        "https://127.0.0.1/cb",
        "ftp://localhost/cb",
        "javascript:alert(1)",
        "http://[::1",
        "http://localhost:99999/cb",
        "",
    ],
)
def test_default_allowlist_rejects_lookalikes_and_foreign_hosts(uri: str) -> None:
    assert not DEFAULT.allows(uri)


@pytest.mark.parametrize(
    "uri", ["https://app.example/cb/abc-123", "https://app.example/cb/A_b-9"]
)
def test_wildcard_entry_accepts_exactly_one_id_segment(uri: str) -> None:
    assert WILDCARD.allows(uri)


@pytest.mark.parametrize(
    "uri",
    [
        "https://app.example/cb/",
        "https://app.example/cb/a/b",
        "https://app.example/cb/../admin",
        "https://app.example/cb/..",
        "https://app.example/cb/a%2Fb",
        "https://app.example/cb/a b",
        "https://app.example:444/cb/abc",
        "https://app.example/other/abc",
    ],
)
def test_wildcard_entry_rejects_other_shapes(uri: str) -> None:
    assert not WILDCARD.allows(uri)


def test_wildcard_entry_does_not_open_loopback() -> None:
    assert not WILDCARD.allows("http://127.0.0.1:1234/cb")


def test_empty_allowlist_allows_nothing() -> None:
    assert not RedirectAllowlist(()).allows(CLAUDE_CALLBACK)


@pytest.mark.parametrize(
    ("uri", "host"),
    [
        (CLAUDE_CALLBACK, "claude.ai"),
        ("http://LocalHost:8080/cb", "localhost"),
        ("http://[::1]:9000/cb", "::1"),
        ("javascript:alert(1)", "?"),
        ("http://[::1", "?"),
        ("", "?"),
    ],
)
def test_host_for_the_consent_screen(uri: str, host: str) -> None:
    assert DEFAULT.host(uri) == host
