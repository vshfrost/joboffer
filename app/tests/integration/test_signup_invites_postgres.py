"""Запрошення на Postgres: у БД лише sha256 токена, погашення атомарне (гонка двох одночасних)."""

import asyncio
import hashlib

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.identity.invites import SignupInviteUseCases
from domain.identity.errors import InviteInvalid
from domain.identity.signup import SignupMode
from infrastructure.db.unit_of_work import unit_of_work_factory
from infrastructure.system import RandomIds, RandomTokens, SystemClock


@pytest.fixture(autouse=True)
def _clean(portal: BlockingPortal, engine: AsyncEngine) -> None:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE signup_invites"))
            await conn.execute(text("TRUNCATE login_failures"))

    portal.call(clean)


@pytest.fixture
def invites(engine: AsyncEngine) -> SignupInviteUseCases:
    return SignupInviteUseCases(
        unit_of_work_factory(engine),
        SystemClock(),
        RandomIds(),
        RandomTokens(),
        SignupMode.INVITE,
    )


def test_database_holds_only_the_sha256_of_the_token(
    portal: BlockingPortal, engine: AsyncEngine, invites: SignupInviteUseCases
) -> None:
    issued = portal.call(invites.create)

    async def rows() -> list[tuple[object, ...]]:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT * FROM signup_invites"))
            return [tuple(row) for row in result]

    stored = portal.call(rows)
    assert len(stored) == 1
    row = stored[0]
    assert hashlib.sha256(issued.token.encode()).hexdigest() in row
    assert issued.token not in [str(value) for value in row]


def test_two_simultaneous_redemptions_succeed_exactly_once(
    portal: BlockingPortal, invites: SignupInviteUseCases
) -> None:
    issued = portal.call(invites.create)

    async def race() -> list[object]:
        return list(
            await asyncio.gather(
                invites.redeem(issued.token),
                invites.redeem(issued.token),
                return_exceptions=True,
            )
        )

    outcomes = portal.call(race)
    failures = [item for item in outcomes if isinstance(item, InviteInvalid)]
    successes = [item for item in outcomes if item is None]
    assert (len(successes), len(failures)) == (1, 1)
