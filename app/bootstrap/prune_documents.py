"""Одноразова чистка старих версій документів: `python -m bootstrap.prune_documents [--apply]`.

У кожного (користувач, вакансія, вид) лишається найновіший документ, решта — рядки (з одноразовими
посиланнями на PDF) і файли PDF — зайва. Без `--apply` лише друкує, що видалила б; з `--apply`
видаляє. Запускати там, де том документів доступний для запису (контейнер `agent`).
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence

from bootstrap.container import build_container
from bootstrap.settings import Settings


async def _prune(settings: Settings, apply: bool) -> int:
    container = build_container(settings)
    try:
        report = await container.documents.prune_superseded(apply)
    finally:
        await container.engine.dispose()
    verb = "Видалено" if report.applied else "Буде видалено (запусти з --apply)"
    sys.stdout.write(
        f"{verb}: документів {report.documents}, файлів PDF на диску {report.files}.\n"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bootstrap.prune_documents",
        description="Лишити лише найновіший документ для кожного (користувач, вакансія, вид).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="справді видалити (без нього — лише підрахунок)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_prune(Settings(), args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
