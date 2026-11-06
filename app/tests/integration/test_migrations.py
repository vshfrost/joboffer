"""Міграції: одна голова, схема = моделі, туди-назад, запуск лише через bootstrap."""

from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from anyio.from_thread import BlockingPortal
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from bootstrap.migrate import main as migrate_main
from infrastructure.db.engine import create_engine
from infrastructure.db.migrate import alembic_config, downgrade, heads, upgrade
from infrastructure.db.schema import metadata


def test_single_head() -> None:
    # Дві голови = дві паралельні гілки з міграціями: перед merge одну треба перешити.
    assert len(heads()) == 1, f"кілька голів Alembic: {heads()}"


def test_models_match_migrations(portal: BlockingPortal, engine: AsyncEngine) -> None:
    def diff(conn: Connection) -> list[object]:
        return list(compare_metadata(MigrationContext.configure(conn), metadata))

    async def run() -> list[object]:
        async with engine.connect() as conn:
            return await conn.run_sync(diff)

    assert portal.call(run) == []


def _tables(conn: Connection) -> list[str]:
    return sorted(inspect(conn).get_table_names())


def _version(conn: Connection) -> str | None:
    return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def test_downgrade_and_upgrade_roundtrip(
    portal: BlockingPortal, scratch_url: str
) -> None:
    async def run() -> tuple[str | None, list[str], str | None]:
        scratch = create_engine(scratch_url)
        try:
            await upgrade(scratch)
            await downgrade(scratch, "base")
            async with scratch.connect() as conn:
                after_down = await conn.run_sync(_tables)
                down_version = await conn.run_sync(_version)
            await upgrade(scratch)
            async with scratch.connect() as conn:
                return down_version, after_down, await conn.run_sync(_version)
        finally:
            await scratch.dispose()

    down_version, tables, up_version = portal.call(run)
    assert (down_version, tables) == (None, ["alembic_version"])
    assert up_version == heads()[0]


def test_bootstrap_migrate_reads_url_from_environment(
    portal: BlockingPortal, scratch_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = "JOBOFFER_DATABASE_URL"
    monkeypatch.setenv(name, scratch_url)

    migrate_main()

    async def version() -> str | None:
        scratch = create_engine(scratch_url)
        try:
            async with scratch.connect() as conn:
                return await conn.run_sync(_version)
        finally:
            await scratch.dispose()

    assert portal.call(version) == heads()[0]


def test_migrations_refuse_to_run_without_connection_from_bootstrap() -> None:
    # Як `alembic upgrade head` з CLI: з'єднання не передано, оточення env.py не читає.
    with pytest.raises(RuntimeError, match=r"bootstrap\.migrate"):
        command.upgrade(alembic_config(), "head")


def test_existing_linkedin_alert_mails_are_marked_processed(
    portal: BlockingPortal, scratch_url: str
) -> None:
    """Алерти, що вже лежать у базі, у вакансії не імпортуються (як у v1 0024); нові листи й
    листи інших видів лишаються необробленими. Колонку читаємо через to_jsonb: до міграції її
    нема, і тест падає на перевірці, а не на SQL."""
    user = "00000000-0000-0000-0000-000000000001"
    insert_mail = text(
        "INSERT INTO mail_messages (user_id, gmail_id, received_at, category, "
        "attachments) VALUES (:user, :gmail_id, now(), :category, '[]')"
    )

    async def run() -> list[tuple[str, bool]]:
        scratch = create_engine(scratch_url)
        try:
            await upgrade(scratch, "0016")
            async with scratch.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, password_hash, "
                        "version, created_at) VALUES (:user, 'a@example.com', 'A', "
                        "'x', 1, now())"
                    ),
                    {"user": user},
                )
                for gmail_id, category in (
                    ("alert", "linkedin_alert"),
                    ("company", "company"),
                ):
                    await conn.execute(
                        insert_mail,
                        {"user": user, "gmail_id": gmail_id, "category": category},
                    )
            await upgrade(scratch)
            async with scratch.connect() as conn:
                found = await conn.execute(
                    text(
                        "SELECT gmail_id, to_jsonb(m) ->> 'alerts_processed_at' IS NOT "
                        "NULL FROM mail_messages m ORDER BY gmail_id"
                    )
                )
                return [(row[0], row[1]) for row in found]
        finally:
            await scratch.dispose()

    assert portal.call(run) == [("alert", True), ("company", False)]


def test_users_have_nullable_terms_columns_and_invites_store_only_digests(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    def columns(conn: Connection) -> dict[str, dict[str, Any]]:
        inspector = inspect(conn)
        return {
            table: {col["name"]: col for col in inspector.get_columns(table)}
            for table in ("users", "signup_invites")
        }

    async def run() -> dict[str, dict[str, Any]]:
        async with engine.connect() as conn:
            return await conn.run_sync(columns)

    found = portal.call(run)
    assert found["users"]["terms_version"]["nullable"] is True
    assert found["users"]["terms_accepted_at"]["nullable"] is True
    assert "token" not in found["signup_invites"]
    assert found["signup_invites"]["token_digest"]["nullable"] is False
    assert found["signup_invites"]["used_at"]["nullable"] is True
