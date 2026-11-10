"""Міграція 0036: у наявних аналізах з'являється порожній список candidate_asks."""

from typing import Any

from anyio.from_thread import BlockingPortal
from sqlalchemy import text

from infrastructure.db.engine import create_engine
from infrastructure.db.migrate import downgrade, upgrade

USER = "00000000-0000-0000-0000-0000000000a1"
JOB = "00000000-0000-0000-0000-0000000000b1"
ANALYSIS = "00000000-0000-0000-0000-0000000000c1"


def test_an_existing_analysis_gets_an_empty_candidate_asks_and_downgrades_cleanly(
    portal: BlockingPortal, scratch_url: str
) -> None:
    async def run() -> tuple[Any, Any]:
        scratch = create_engine(scratch_url)
        query = text("SELECT details FROM job_analyses")
        try:
            await upgrade(scratch, "0035")
            async with scratch.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, password_hash, "
                        "version, created_at) "
                        "VALUES (:id, 'a@example.com', 'U', 'x', 1, now())"
                    ),
                    {"id": USER},
                )
                await conn.execute(
                    text(
                        "INSERT INTO jobs (id, user_id, job_number, created_at) "
                        "VALUES (:id, :user, 1, now())"
                    ),
                    {"id": JOB, "user": USER},
                )
                await conn.execute(
                    text(
                        "INSERT INTO job_analyses (id, user_id, job_id, score, "
                        "filters_passed, details, updated_at) VALUES "
                        "(:id, :user, :job, 50, true, "
                        """'{"summary": "S", "must_have": ["Python"]}', now())"""
                    ),
                    {"id": ANALYSIS, "user": USER, "job": JOB},
                )
            await upgrade(scratch, "0036")
            async with scratch.connect() as conn:
                after = (await conn.execute(query)).scalar_one()
            await downgrade(scratch, "0035")
            async with scratch.connect() as conn:
                before = (await conn.execute(query)).scalar_one()
            return after, before
        finally:
            await scratch.dispose()

    after, before = portal.call(run)
    assert after == {"summary": "S", "must_have": ["Python"], "candidate_asks": []}
    assert before == {"summary": "S", "must_have": ["Python"]}
