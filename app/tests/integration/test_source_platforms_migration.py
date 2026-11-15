"""Міграція 0038: `source_companies.platform` приймає smartrecruiters і workable; невідома платформа
й далі відхиляється. Назад: компанії нових платформ видаляються, обмеження повертається."""

from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from infrastructure.db.engine import create_engine
from infrastructure.db.migrate import downgrade, upgrade

USER = "00000000-0000-0000-0000-0000000000a1"
INSERT = text(
    "INSERT INTO source_companies (id, user_id, platform, slug, name, enabled) "
    "VALUES (gen_random_uuid(), :user, :platform, 'acme', 'Acme', true)"
)


def test_new_platforms_are_accepted_unknown_is_rejected_and_downgrade_restores_the_check(
    portal: BlockingPortal, scratch_url: str
) -> None:
    async def run() -> tuple[str, str, list[str], list[str], str]:
        scratch = create_engine(scratch_url)

        async def insert(platform: str) -> str:
            try:
                async with scratch.begin() as conn:
                    await conn.execute(INSERT, {"user": USER, "platform": platform})
            except IntegrityError:
                return "rejected"
            return "accepted"

        async def platforms() -> list[str]:
            async with scratch.connect() as conn:
                rows = await conn.execute(
                    text("SELECT platform FROM source_companies ORDER BY platform")
                )
                return [row[0] for row in rows]

        try:
            await upgrade(scratch, "0037")
            async with scratch.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, password_hash, "
                        "version, created_at) "
                        "VALUES (:id, 'a@example.com', 'U', 'x', 1, now())"
                    ),
                    {"id": USER},
                )
            before = await insert("workable")
            await upgrade(scratch, "0038")
            after = [await insert("smartrecruiters"), await insert("workable")]
            unknown = await insert("workday")
            existing = await platforms()
            await downgrade(scratch, "0037")
            return before, unknown, after, existing, await insert("workable")
        finally:
            await scratch.dispose()

    before, unknown, after, existing, again = portal.call(run)
    assert before == "rejected"
    assert after == ["accepted", "accepted"]
    assert unknown == "rejected"
    assert existing == ["smartrecruiters", "workable"]
    assert again == "rejected"
