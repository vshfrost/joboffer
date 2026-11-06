"""Integration-тести: справжні зовнішні сервіси (testcontainers, потрібен Docker). Не входять у core-only."""

from collections.abc import Iterator

import anyio
import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.community.postgres import PostgresContainer

from infrastructure.db.engine import create_engine
from infrastructure.db.migrate import upgrade
from tests.support.core_conftest import portal

__all__ = ["portal"]

POSTGRES_IMAGE = "postgres:18.6-trixie"  # той самий тег, що в infra/compose.yaml


async def _migrate(url: str) -> None:
    engine = create_engine(url)
    try:
        await upgrade(engine)
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Один Postgres на прогін, схема — до head."""
    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg") as pg:
        url = pg.get_connection_url()
        anyio.run(_migrate, url)
        yield url


@pytest.fixture
def engine(portal: BlockingPortal, database_url: str) -> Iterator[AsyncEngine]:
    """Engine живе в event loop порталу: створення, запити й dispose — через `portal.call`."""
    engine = create_engine(database_url)
    yield engine
    portal.call(engine.dispose)


@pytest.fixture
def scratch_url(portal: BlockingPortal, engine: AsyncEngine) -> Iterator[str]:
    """Окрема порожня база на тому ж сервері — для тестів, що ганяють міграції туди-назад."""
    admin = engine.execution_options(isolation_level="AUTOCOMMIT")

    async def execute(sql: str) -> None:
        async with admin.connect() as conn:
            await conn.execute(text(sql))

    portal.call(execute, "CREATE DATABASE scratch")
    yield engine.url.set(database="scratch").render_as_string(hide_password=False)
    portal.call(execute, "DROP DATABASE scratch WITH (FORCE)")
