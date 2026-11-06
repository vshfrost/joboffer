"""Прод-compose: кожен сервіс має ліміт памʼяті, щоб один процес не зʼїв увесь хост."""

import re
from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[3] / "infra" / "compose.prod.yaml"
MEMORY = re.compile(r"^\d+[mg]$")


def services() -> dict[str, str]:
    text = COMPOSE.read_text(encoding="utf-8")
    block = text.split("\nservices:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    parts = re.split(r"^  (\w+):\n", block, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_every_service_is_found() -> None:
    assert set(services()) == {
        "postgres",
        "app",
        "agent",
        "web",
        "cloudflared",
        "sources",
        "triage",
        "mailsync",
    }


def test_every_service_has_a_memory_limit() -> None:
    missing = []
    for name, body in services().items():
        found = re.search(r"^    mem_limit: (\S+)$", body, flags=re.MULTILINE)
        if found is None or not MEMORY.match(found.group(1)):
            missing.append(name)

    assert missing == []
