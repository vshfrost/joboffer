"""Репозиторії онбордингу на справжній базі: підказки на користувача, «живий» грант Claude, адреса пошти без створення."""

from datetime import timedelta
from uuid import UUID

from anyio.from_thread import BlockingPortal
from sqlalchemy import text

from domain.identity.ids import GrantId, UserId
from domain.identity.session import TokenDigest
from domain.oauth.entities import Grant, OAuthClient, StoredToken, TokenKind
from domain.oauth.ids import ClientId
from domain.onboarding.steps import TipState
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, uow

__all__ = ["uow"]

CLIENT = ClientId(UUID(int=0xC1))
LATER = NOW + timedelta(hours=1)


async def _seed_client(uow: UnitOfWorkFactory) -> None:
    async with uow() as tx:
        # Клієнти не належать користувачам, тож `TRUNCATE users CASCADE` у фікстурі їх не прибирає.
        await tx.session.execute(text("TRUNCATE oauth_clients CASCADE"))
        await tx.oauth_clients.add(
            OAuthClient(
                id=CLIENT, name="Claude", redirect_uris=("https://c/cb",), metadata={}
            )
        )
        await tx.commit()


async def _grant(
    uow: UnitOfWorkFactory,
    user: UserId,
    number: int,
    *,
    refresh_expires: timedelta = timedelta(days=30),
    consumed: bool = False,
    revoked: bool = False,
    refresh: bool = True,
) -> None:
    grant_id = GrantId(UUID(int=0x600 + number))
    async with uow() as tx:
        await tx.grants.add(
            Grant(
                id=grant_id,
                user_id=user,
                client_id=CLIENT,
                resource="https://r",
                created_at=NOW,
                revoked_at=NOW if revoked else None,
            )
        )
        kinds = (
            (TokenKind.ACCESS, TokenKind.REFRESH) if refresh else (TokenKind.ACCESS,)
        )
        for kind in kinds:
            await tx.oauth_tokens.add(
                StoredToken(
                    digest=TokenDigest.from_token(f"{kind}-{number}"),
                    kind=kind,
                    grant_id=grant_id,
                    expires_at=NOW + refresh_expires,
                    consumed_at=NOW if consumed and kind is TokenKind.REFRESH else None,
                )
            )
        await tx.commit()


async def _live(uow: UnitOfWorkFactory, user: UserId) -> bool:
    async with uow() as tx:
        return await tx.grants.has_live(user, NOW)


def test_an_active_grant_with_a_valid_refresh_token_is_live(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_client, uow)
    portal.call(lambda: _grant(uow, ALICE, 1))
    assert portal.call(_live, uow, ALICE) is True


def test_no_grant_is_not_live(portal: BlockingPortal, uow: UnitOfWorkFactory) -> None:
    portal.call(_seed_client, uow)
    assert portal.call(_live, uow, ALICE) is False


def test_a_revoked_grant_is_not_live(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_client, uow)
    portal.call(lambda: _grant(uow, ALICE, 1, revoked=True))
    assert portal.call(_live, uow, ALICE) is False


def test_a_grant_whose_refresh_token_expired_is_not_live(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_client, uow)
    portal.call(lambda: _grant(uow, ALICE, 1, refresh_expires=timedelta(0)))
    assert portal.call(_live, uow, ALICE) is False


def test_a_grant_whose_refresh_token_was_used_is_not_live(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_client, uow)
    portal.call(lambda: _grant(uow, ALICE, 1, consumed=True))
    assert portal.call(_live, uow, ALICE) is False


def test_a_grant_with_only_an_access_token_is_not_live(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_client, uow)
    portal.call(lambda: _grant(uow, ALICE, 1, refresh=False))
    assert portal.call(_live, uow, ALICE) is False


def test_another_users_live_grant_is_not_mine(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seed_client, uow)
    portal.call(lambda: _grant(uow, BOB, 1))
    assert portal.call(_live, uow, ALICE) is False
    assert portal.call(_live, uow, BOB) is True


# --- підказки ---------------------------------------------------------------------------------


async def _tips(uow: UnitOfWorkFactory, user: UserId) -> list[TipState]:
    async with uow() as tx:
        return sorted(await tx.onboarding_tips.all(user), key=lambda tip: tip.key)


async def _seen(uow: UnitOfWorkFactory, user: UserId, key: str, at: object) -> None:
    async with uow() as tx:
        await tx.onboarding_tips.mark_seen(user, key, at)  # type: ignore[arg-type]
        await tx.commit()


async def _dismiss(uow: UnitOfWorkFactory, user: UserId, key: str, at: object) -> None:
    async with uow() as tx:
        await tx.onboarding_tips.dismiss(user, key, at)  # type: ignore[arg-type]
        await tx.commit()


def test_no_rows_means_no_tips_seen(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    assert portal.call(_tips, uow, ALICE) == []


def test_marking_seen_twice_keeps_the_first_time(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seen, uow, ALICE, "goal", NOW)
    portal.call(_seen, uow, ALICE, "goal", LATER)
    assert portal.call(_tips, uow, ALICE) == [TipState("goal", NOW, None)]


def test_dismissing_an_unseen_tip_also_marks_it_seen(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_dismiss, uow, ALICE, "claude", NOW)
    assert portal.call(_tips, uow, ALICE) == [TipState("claude", NOW, NOW)]


def test_dismissing_a_seen_tip_keeps_when_it_was_first_seen(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_seen, uow, ALICE, "photo", NOW)
    portal.call(_dismiss, uow, ALICE, "photo", LATER)
    portal.call(_dismiss, uow, ALICE, "photo", LATER + timedelta(minutes=1))
    assert portal.call(_tips, uow, ALICE) == [TipState("photo", NOW, LATER)]


def test_marking_seen_after_dismissing_does_not_undo_it(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_dismiss, uow, ALICE, "mail", NOW)
    portal.call(_seen, uow, ALICE, "mail", LATER)
    assert portal.call(_tips, uow, ALICE) == [TipState("mail", NOW, NOW)]


def test_tips_are_per_user(portal: BlockingPortal, uow: UnitOfWorkFactory) -> None:
    portal.call(_dismiss, uow, ALICE, "goal", NOW)
    portal.call(_seen, uow, BOB, "goal", LATER)
    assert portal.call(_tips, uow, ALICE) == [TipState("goal", NOW, NOW)]
    assert portal.call(_tips, uow, BOB) == [TipState("goal", LATER, None)]


# --- адреса пошти -----------------------------------------------------------------------------


def test_finding_a_mail_address_does_not_create_one(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def find_twice() -> tuple[object, object]:
        async with uow() as tx:
            first = await tx.mail_inboxes.find(ALICE)
        async with uow() as tx:
            return first, await tx.mail_inboxes.find(ALICE)

    assert portal.call(find_twice) == (None, None)


def test_find_returns_the_address_made_by_ensure_and_only_to_its_owner(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[bool, bool]:
        async with uow() as tx:
            made = await tx.mail_inboxes.ensure(ALICE)
            await tx.commit()
        async with uow() as tx:
            mine = await tx.mail_inboxes.find(ALICE)
            theirs = await tx.mail_inboxes.find(BOB)
        return mine is not None and mine.tag == made.tag, theirs is None

    assert portal.call(run) == (True, True)
