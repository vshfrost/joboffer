"""Unit of work на справжньому Postgres: commit фіксує, усе інше відкочує."""

from collections.abc import Iterator

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from infrastructure.db.unit_of_work import UnitOfWorkFactory, unit_of_work_factory


class Boom(Exception):
    pass


@pytest.fixture
def uow(portal: BlockingPortal, engine: AsyncEngine) -> Iterator[UnitOfWorkFactory]:
    async def execute(sql: str) -> None:
        async with engine.begin() as conn:
            await conn.execute(text(sql))

    portal.call(execute, "CREATE TABLE uow_probe (value text NOT NULL)")
    yield unit_of_work_factory(engine)
    portal.call(execute, "DROP TABLE uow_probe")


async def _insert(uow: UnitOfWorkFactory, value: str, *, commit: bool) -> None:
    async with uow() as tx:
        await tx.session.execute(
            text("INSERT INTO uow_probe (value) VALUES (:value)"), {"value": value}
        )
        if commit:
            await tx.commit()


async def _values(uow: UnitOfWorkFactory) -> list[str]:
    async with uow() as tx:
        rows = await tx.session.execute(
            text("SELECT value FROM uow_probe ORDER BY value")
        )
        return list(rows.scalars())


def test_commit_persists(portal: BlockingPortal, uow: UnitOfWorkFactory) -> None:
    portal.call(lambda: _insert(uow, "a", commit=True))
    assert portal.call(_values, uow) == ["a"]


def test_without_commit_everything_rolls_back(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(lambda: _insert(uow, "a", commit=False))
    assert portal.call(_values, uow) == []


def test_error_rolls_back(portal: BlockingPortal, uow: UnitOfWorkFactory) -> None:
    async def fail() -> None:
        async with uow() as tx:
            await tx.session.execute(text("INSERT INTO uow_probe (value) VALUES ('a')"))
            raise Boom

    with pytest.raises(Boom):
        portal.call(fail)
    assert portal.call(_values, uow) == []


def test_session_is_only_available_inside_the_block(uow: UnitOfWorkFactory) -> None:
    with pytest.raises(RuntimeError, match="async with"):
        _ = uow().session
