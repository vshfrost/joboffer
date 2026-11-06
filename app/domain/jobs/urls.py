"""Нормалізація посилань на вакансії: однакова вакансія з різних розсилок має давати один URL.

Без `urllib` (домен його не імпортує): посилання розбирає регулярний вираз, параметри запиту
не перекодовуються — лише відкидаються трекінгові.
"""

import re

from domain.shared.errors import InvalidValue

# Трекінгові параметри (крім utm_*): однакова вакансія з різних розсилок дає один URL.
TRACKING_PARAMS = frozenset({"gclid", "fbclid", "refid", "trackingid", "trk"})
_URL = re.compile(
    r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://(?P<host>[^/?#]*)(?P<path>[^?#]*)"
    r"(?:\?(?P<query>[^#]*))?(?:#.*)?",
)
_NOT_HTTP = "Посилання має починатися з http:// або https://."


def normalize_url(raw: str) -> str:
    """http(s)-посилання без фрагмента, utm_* і трекінгових параметрів; хост у нижньому регістрі."""
    found = _URL.fullmatch(raw.strip())
    if found is None or found["scheme"].lower() not in {"http", "https"}:
        raise InvalidValue("url", _NOT_HTTP)
    if not found["host"]:
        raise InvalidValue("url", _NOT_HTTP)
    path = found["path"].rstrip("/") or "/"
    query = "&".join(
        part
        for part in (found["query"] or "").split("&")
        if part and not _is_tracking(part.partition("=")[0])
    )
    base = f"{found['scheme'].lower()}://{found['host'].lower()}{path}"
    return f"{base}?{query}" if query else base


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith("utm_") or lowered in TRACKING_PARAMS
