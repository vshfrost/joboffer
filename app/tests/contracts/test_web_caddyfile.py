"""Caddy веба віддає заголовки безпеки (HSTS, CSP з worker для ALTCHA, frame-ancestors, nosniff, Referrer-Policy)."""

import re
from pathlib import Path

CADDYFILE = Path(__file__).resolve().parents[3] / "infra" / "web" / "Caddyfile"


def header_value(name: str) -> str:
    text = CADDYFILE.read_text(encoding="utf-8")
    match = re.search(
        rf'^\s*\??{re.escape(name)}\s+"?([^"\n]+)"?\s*$', text, re.MULTILINE
    )
    assert match, f"у Caddyfile нема заголовка {name}"
    return match.group(1)


def csp_directives() -> dict[str, str]:
    parts = (p.strip() for p in header_value("Content-Security-Policy").split(";"))
    return {p.split(" ", 1)[0]: p.partition(" ")[2] for p in parts if p}


def test_hsts_is_sent_for_a_long_time() -> None:
    value = header_value("Strict-Transport-Security")
    assert int(re.search(r"max-age=(\d+)", value).group(1)) >= 31536000  # type: ignore[union-attr]


def test_nosniff() -> None:
    assert header_value("X-Content-Type-Options") == "nosniff"


def test_referrer_policy() -> None:
    assert header_value("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_csp_forbids_framing() -> None:
    assert csp_directives()["frame-ancestors"] == "'none'"


def test_csp_allows_the_altcha_worker() -> None:
    assert csp_directives()["worker-src"] == "'self' blob:"


def test_csp_defaults_to_same_origin_without_inline_scripts() -> None:
    directives = csp_directives()
    assert directives["default-src"] == "'self'"
    assert "unsafe" not in directives["script-src"]
    assert directives["object-src"] == "'none'"


def test_headers_are_set_inside_the_site_block() -> None:
    text = CADDYFILE.read_text(encoding="utf-8")
    assert text.find(":8080 {") != -1
    assert text.find("Strict-Transport-Security") > text.find(":8080 {")


def spa_handler() -> str:
    text = CADDYFILE.read_text(encoding="utf-8")
    match = re.search(r"^\s*handle\s+(@\w+)\s*\{", text, re.MULTILINE)
    assert match, "у Caddyfile нема handle для SPA"
    return match.group(1)


def spa_matcher() -> str:
    text = CADDYFILE.read_text(encoding="utf-8")
    match = re.search(rf"^\s*{re.escape(spa_handler())}\s+(.+)$", text, re.MULTILINE)
    assert match, "у Caddyfile нема named matcher SPA"
    return match.group(1)


def test_spa_is_served_from_the_root_with_index_fallback() -> None:
    text = CADDYFILE.read_text(encoding="utf-8")
    assert "root * /srv/app" in text
    assert "try_files {path} /index.html" in text
    assert "redir" not in text


def test_spa_does_not_take_api_mcp_and_oauth_discovery() -> None:
    matcher = spa_matcher()
    assert matcher.startswith("not path")
    for path in ("/api/*", "/mcp*", "/.well-known/*"):
        assert path in matcher.split()


def handler_block(opening: str) -> str:
    """Тіло блока `handle…`, що починається з рядка `opening` (до закриття на тому ж відступі)."""
    text = CADDYFILE.read_text(encoding="utf-8")
    match = re.search(
        rf"^(\s*){re.escape(opening)}\s*\{{\n(.*?)^\1\}}",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"у Caddyfile нема блока {opening}"
    return match.group(2)


def test_headers_do_not_override_those_the_upstream_sets() -> None:
    """HTML логіна MCP має суворіші CSP і Referrer-Policy та без form-action: префікс `?` лишає їх."""
    text = CADDYFILE.read_text(encoding="utf-8")
    for name in (
        "Content-Security-Policy",
        "Referrer-Policy",
        "X-Content-Type-Options",
    ):
        assert re.search(rf"^\s*\?{name}\s", text, re.MULTILINE), (
            f"{name} має ставитись лише за відсутності"
        )


def test_api_goes_to_the_app_without_the_api_prefix() -> None:
    assert "reverse_proxy {$APP_UPSTREAM:app:8797}" in handler_block(
        "handle_path /api/*"
    )


def test_mcp_and_oauth_discovery_go_to_the_agent_with_the_path_kept() -> None:
    text = CADDYFILE.read_text(encoding="utf-8")
    matcher = re.search(r"^\s*@agent\s+path\s+(.+)$", text, re.MULTILINE)
    assert matcher, "у Caddyfile нема matcher агента"
    assert matcher.group(1).split() == ["/mcp*", "/.well-known/oauth-*"]
    body = handler_block("handle @agent")
    assert "reverse_proxy {$AGENT_UPSTREAM:agent:8798}" in body
    assert "rewrite" not in body
    assert "uri " not in body


def test_agent_responses_are_streamed_without_buffering() -> None:
    assert "flush_interval -1" in handler_block("handle @agent")


def test_other_well_known_paths_are_not_the_spa() -> None:
    assert "respond 404" in handler_block("handle /.well-known/*")
