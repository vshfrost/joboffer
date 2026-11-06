"""Міграції бази до head. Запуск: `python -m bootstrap.migrate` (так робить контейнер перед API)."""

import asyncio
import logging

from bootstrap.settings import Settings
from infrastructure.db.engine import create_engine
from infrastructure.db.migrate import upgrade


async def _migrate(url: str) -> None:
    engine = create_engine(url)
    try:
        await upgrade(engine)
    finally:
        await engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s"
    )
    asyncio.run(_migrate(Settings().database_url.get_secret_value()))


if __name__ == "__main__":
    main()
