"""Міграція 0031: відповіді на прогалини вакансій і їхні факти."""

from anyio.from_thread import BlockingPortal
from sqlalchemy import text

from infrastructure.db.engine import create_engine
from infrastructure.db.migrate import downgrade, upgrade


def test_the_migration_adds_the_answer_tables_and_downgrades_cleanly(
    portal: BlockingPortal, scratch_url: str
) -> None:
    async def run() -> tuple[set[str], set[str]]:
        scratch = create_engine(scratch_url)
        query = text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ('gap_answers', 'gap_answer_facts')"
        )
        try:
            await upgrade(scratch)
            async with scratch.connect() as conn:
                after = {row[0] for row in await conn.execute(query)}
            await downgrade(scratch, "0030")
            async with scratch.connect() as conn:
                before = {row[0] for row in await conn.execute(query)}
            return after, before
        finally:
            await scratch.dispose()

    after, before = portal.call(run)
    assert after == {"gap_answers", "gap_answer_facts"}
    assert before == set()
