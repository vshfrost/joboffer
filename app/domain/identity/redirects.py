"""Куди вести користувача після входу: лише внутрішній шлях застосунку (те саме правило, що й у вебі)."""

import re

HOME = "/"
_LOGIN_PATH = "/login"


def _ambiguous(value: str) -> bool:
    # Браузер прибирає з адреси табуляції й переноси та читає `\` як `/`: `/\t/evil` — це `//evil`.
    return any(not char.isprintable() or char == "\\" for char in value)


def safe_next_path(raw: str | None) -> str:
    """Внутрішній шлях; будь-що інше (і сам екран входу, щоб вхід не зациклився) веде на головну."""
    if (
        raw is None
        or not raw.startswith("/")
        or raw.startswith("//")
        or _ambiguous(raw)
    ):
        return HOME
    path = re.split(r"[?#]", raw, maxsplit=1)[0]
    if path == _LOGIN_PATH or path.startswith(f"{_LOGIN_PATH}/"):
        return HOME
    return raw
