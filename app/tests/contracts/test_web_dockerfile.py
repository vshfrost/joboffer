"""Образ веба (Caddy) працює не від root і слухає той самий порт 8080."""

import re
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[3] / "infra" / "docker" / "web.Dockerfile"
CADDYFILE = DOCKERFILE.parents[1] / "web" / "Caddyfile"


def final_stage() -> list[str]:
    lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("FROM ")]
    return lines[starts[-1] :]


def test_final_stage_switches_to_a_non_root_user() -> None:
    users = [
        line.split(maxsplit=1)[1].strip()
        for line in final_stage()
        if line.startswith("USER ")
    ]

    assert users, "в останньому stage нема USER: Caddy працює від root"
    assert users[-1] not in {"root", "0", "0:0", "root:root"}


def test_user_is_created_in_the_image_and_owns_caddy_state() -> None:
    stage = "\n".join(final_stage())

    assert re.search(r"adduser\b", stage)
    assert re.search(
        r"chown\b.*\s/config\b.*\s/data\b|chown\b.*\s/data\b.*\s/config\b", stage
    )


def test_port_stays_8080() -> None:
    assert "EXPOSE 8080" in final_stage()
    assert ":8080 {" in CADDYFILE.read_text(encoding="utf-8")
