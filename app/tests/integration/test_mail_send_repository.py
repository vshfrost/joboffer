"""Журнал відправлень на справжній базі: лічильник листів за вікно часу для добового ліміту."""

from datetime import UTC, datetime, timedelta

from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from infrastructure.db.unit_of_work import UnitOfWorkFactory, unit_of_work_factory

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)


def test_count_includes_only_sends_after_the_moment(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    async def run() -> tuple[int, int]:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE mail_sends"))
        factory: UnitOfWorkFactory = unit_of_work_factory(engine)
        async with factory() as tx:
            await tx.mail_sends.record(NOW - timedelta(hours=25))
            await tx.mail_sends.record(NOW - timedelta(hours=23))
            await tx.mail_sends.record(NOW - timedelta(minutes=1))
            await tx.commit()
        async with factory() as tx:
            return (
                await tx.mail_sends.count_since(NOW - timedelta(hours=24)),
                await tx.mail_sends.count_since(NOW),
            )

    assert portal.call(run) == (2, 0)


def test_a_send_is_not_recorded_without_commit(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    async def run() -> int:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE mail_sends"))
        factory = unit_of_work_factory(engine)
        async with factory() as tx:
            await tx.mail_sends.record(NOW)
        async with factory() as tx:
            return await tx.mail_sends.count_since(NOW - timedelta(hours=1))

    assert portal.call(run) == 0
