"""Allowlist адрес повернення на stdlib `urllib.parse`: порівнюються розібрані частини, а не рядок.

Запис — точна адреса; «…/*» — рівно один сегмент-ID у кінці; «loopback» — http на 127.0.0.1 / localhost / [::1].
`https://claude.ai@evil/…`, чужий порт, фрагмент чи `../` у сегменті не проходять.
"""

import re
from urllib.parse import SplitResult, urlsplit

from domain.oauth.redirect import DEFAULT_ENTRIES, LOOPBACK

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ID_SEGMENT = re.compile(r"[A-Za-z0-9_-]{1,128}")
# urlsplit мовчки прибирає табуляції й переноси, а браузер читає `\` як `/`: такі адреси не пропускаємо.
_AMBIGUOUS = re.compile(r"[\x00-\x20\x7f\\]")


def _split(uri: str) -> tuple[SplitResult, int | None] | None:
    if _AMBIGUOUS.search(uri):
        return None
    try:
        parts = urlsplit(uri)
        port = parts.port
    except ValueError:
        return None
    return parts, port


class RedirectAllowlist:
    def __init__(self, entries: tuple[str, ...] = DEFAULT_ENTRIES) -> None:
        self._entries = entries

    def allows(self, uri: str) -> bool:
        split = _split(uri)
        if split is None:
            return False
        parts, port = split
        if (
            parts.username is not None
            or parts.password is not None
            or parts.fragment
            or not parts.hostname
        ):
            return False
        return any(_matches(parts, port, entry) for entry in self._entries)

    def host(self, uri: str) -> str:
        split = _split(uri)
        return "?" if split is None or not split[0].hostname else split[0].hostname


def _matches(parts: SplitResult, port: int | None, entry: str) -> bool:
    if entry == LOOPBACK:
        return parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS
    allowed = urlsplit(entry)
    if (parts.scheme, parts.hostname, port, parts.query) != (
        allowed.scheme,
        allowed.hostname,
        allowed.port,
        allowed.query,
    ):
        return False
    if allowed.path.endswith("/*"):
        base = allowed.path[:-1]
        return parts.path.startswith(base) and bool(
            _ID_SEGMENT.fullmatch(parts.path[len(base) :])
        )
    return parts.path == allowed.path
