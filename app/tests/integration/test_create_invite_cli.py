"""CLI `python -m bootstrap.create_invite`: друкує посилання, у БД лише sha256 токена."""

import hashlib

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bootstrap.create_invite import main


@pytest.fixture(autouse=True)
def _environment(
    portal: BlockingPortal,
    engine: AsyncEngine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE signup_invites"))

    portal.call(clean)
    monkeypatch.setenv("JOBOFFER_DATABASE_URL", database_url)
    monkeypatch.setenv("JOBOFFER_WEB_PUBLIC_URL", "https://jobs.example.com")


def test_prints_the_signup_link_and_stores_only_the_digest(
    portal: BlockingPortal,
    engine: AsyncEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 0
    printed = capsys.readouterr().out.strip()
    prefix = "https://jobs.example.com/signup?invite="
    assert printed.startswith(prefix)
    token = printed.removeprefix(prefix)
    assert len(token) >= 43

    async def digests() -> list[str]:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT token_digest FROM signup_invites"))
            return [row[0] for row in result]

    assert portal.call(digests) == [hashlib.sha256(token.encode()).hexdigest()]


def test_each_run_creates_a_new_invite(capsys: pytest.CaptureFixture[str]) -> None:
    main([])
    first = capsys.readouterr().out
    main([])
    assert capsys.readouterr().out != first
