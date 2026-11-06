"""Alembic через готове з'єднання. URL бази сюди передає bootstrap, env.py оточення не читає."""

from collections.abc import Callable

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

SCRIPT_LOCATION = "infrastructure.db:migrations"


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    return config


def heads() -> tuple[str, ...]:
    return tuple(ScriptDirectory.from_config(alembic_config()).get_heads())


async def upgrade(engine: AsyncEngine, revision: str = "head") -> None:
    await _run(engine, command.upgrade, revision)


async def downgrade(engine: AsyncEngine, revision: str) -> None:
    await _run(engine, command.downgrade, revision)


async def _run(
    engine: AsyncEngine, action: Callable[[Config, str], None], revision: str
) -> None:
    def run(connection: Connection) -> None:
        config = alembic_config()
        config.attributes["connection"] = connection
        action(config, revision)

    async with engine.begin() as connection:
        await connection.run_sync(run)
