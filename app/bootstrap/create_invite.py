"""CLI створення запрошення на реєстрацію: `python -m bootstrap.create_invite`.

Друкує посилання `<web_public_url>/signup?invite=<токен>`. Токен показується лише тут, один раз:
у БД лежить його sha256. Вихідний код 0 — створено.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence

from bootstrap.container import build_container
from bootstrap.settings import Settings


async def _create(settings: Settings) -> int:
    container = build_container(settings)
    try:
        issued = await container.invites.create()
    finally:
        await container.engine.dispose()
    base = settings.web_public_url.rstrip("/")
    sys.stdout.write(f"{base}/signup?invite={issued.token}\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(
        prog="python -m bootstrap.create_invite",
        description="Створити одноразове запрошення (дійсне 7 днів) і надрукувати посилання.",
    ).parse_args(argv)
    return asyncio.run(_create(Settings()))


if __name__ == "__main__":
    raise SystemExit(main())
