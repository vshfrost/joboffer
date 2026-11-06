"""Міграція джерел (0018): таблиці з UUID-ключами й унікальністю «користувач + платформа + слаг»
та «користувач + джерело + запит»."""

from typing import Any

from anyio.from_thread import BlockingPortal
from sqlalchemy import Connection, Uuid, inspect
from sqlalchemy.ext.asyncio import AsyncEngine

TABLES = {
    "source_companies",
    "source_feeds",
    "source_company_runs",
    "source_feed_runs",
}


class Schema:
    def __init__(self, portal: BlockingPortal, engine: AsyncEngine) -> None:
        self._portal = portal
        self._engine = engine

    def _read(self, read: Any) -> Any:
        async def run() -> Any:
            async with self._engine.connect() as conn:
                return await conn.run_sync(read)

        return self._portal.call(run)

    def tables(self) -> set[str]:
        def read(conn: Connection) -> set[str]:
            return set(inspect(conn).get_table_names())

        found: set[str] = self._read(read)
        return found

    def uniques(self, table: str) -> list[set[str]]:
        def read(conn: Connection) -> list[set[str]]:
            return [
                set(u["column_names"])
                for u in inspect(conn).get_unique_constraints(table)
            ]

        found: list[set[str]] = self._read(read)
        return found

    def column_type(self, table: str, column: str) -> Any:
        def read(conn: Connection) -> Any:
            return {c["name"]: c["type"] for c in inspect(conn).get_columns(table)}

        types: dict[str, Any] = self._read(read)
        return types[column]


def test_migration_creates_the_sources_tables(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    assert Schema(portal, engine).tables() >= TABLES


def test_companies_are_unique_per_user_platform_and_slug(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    assert {"user_id", "platform", "slug"} in Schema(portal, engine).uniques(
        "source_companies"
    )


def test_feeds_are_unique_per_user_source_and_query(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    assert {"user_id", "source", "query"} in Schema(portal, engine).uniques(
        "source_feeds"
    )


def test_source_ids_are_uuids(portal: BlockingPortal, engine: AsyncEngine) -> None:
    schema = Schema(portal, engine)

    assert isinstance(schema.column_type("source_companies", "id"), Uuid)
    assert isinstance(schema.column_type("source_feeds", "id"), Uuid)
    assert isinstance(schema.column_type("source_company_runs", "company_id"), Uuid)
    assert isinstance(schema.column_type("source_feed_runs", "feed_id"), Uuid)
