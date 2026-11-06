"""Міграція 0030: наявні факти стають джерелом cv без вакансії."""

from typing import Any

from anyio.from_thread import BlockingPortal
from sqlalchemy import text

from infrastructure.db.engine import create_engine
from infrastructure.db.migrate import upgrade

USER = "00000000-0000-0000-0000-0000000000a1"
FACT = "00000000-0000-0000-0000-0000000000f1"


def test_existing_facts_become_cv_facts_without_a_job(
    portal: BlockingPortal, scratch_url: str
) -> None:
    async def run() -> dict[str, Any]:
        scratch = create_engine(scratch_url)
        try:
            await upgrade(scratch, "0029")
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
                        "INSERT INTO facts (id, user_id, fact_number, kind, text, "
                        "text_hash, confirmed, created_at, updated_at) VALUES "
                        "(:id, :user, 1, 'skill', 'Python', 'h', true, now(), now())"
                    ),
                    {"id": FACT, "user": USER},
                )
            await upgrade(scratch)
            async with scratch.connect() as conn:
                found = await conn.execute(text("SELECT to_jsonb(f) FROM facts f"))
                return dict(found.scalar_one())
        finally:
            await scratch.dispose()

    row = portal.call(run)
    assert "job_id" in row
    assert (row.get("source"), row["job_id"], row["confirmed"]) == ("cv", None, True)
