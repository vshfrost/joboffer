"""Каталог джерел на справжній базі: унікальність «користувач + ціль» навіть при гонці двох додавань,
видалення разом зі станом прогону й збереження стану джерела, якого вже нема."""

from uuid import UUID

from anyio.from_thread import BlockingPortal

from application.ports.sources import SourceGone
from domain.identity.ids import UserId
from domain.sources.ids import SourceId
from domain.sources.kinds import FeedSource, Platform
from domain.sources.manage import Company, Feed
from domain.sources.run import SourceRun, Subscription
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, uow
from tests.integration.test_sources_repository import (
    COMPANY_RUNS,
    Db,
    db,
)

__all__ = ["db", "uow"]


def company(number: int, slug: str = "acme") -> Company:
    return Company(SourceId(UUID(int=number)), Platform.GREENHOUSE, slug, "Acme", True)


def feed(number: int, query: str = "category=Python") -> Feed:
    return Feed(SourceId(UUID(int=number)), FeedSource.DOU, query, True)


def test_the_same_company_is_added_once_per_user(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    async def add() -> list[bool]:
        async with uow() as tx:
            added = [
                await tx.source_catalog.add_company(ALICE, company(1)),
                await tx.source_catalog.add_company(ALICE, company(2)),
                await tx.source_catalog.add_company(BOB, company(3)),
            ]
            await tx.commit()
            return added

    assert portal.call(add) == [True, False, True]
    assert db.rows("SELECT id FROM source_companies ORDER BY id") == [
        (UUID(int=1),),
        (UUID(int=3),),
    ]


def test_the_same_feed_is_added_once_per_user(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    async def add() -> list[bool]:
        async with uow() as tx:
            added = [
                await tx.source_catalog.add_feed(ALICE, feed(1)),
                await tx.source_catalog.add_feed(ALICE, feed(2)),
                await tx.source_catalog.add_feed(BOB, feed(3)),
            ]
            await tx.commit()
            return added

    assert portal.call(add) == [True, False, True]
    assert db.rows("SELECT id FROM source_feeds ORDER BY id") == [
        (UUID(int=1),),
        (UUID(int=3),),
    ]


def test_a_company_is_changed_and_deleted_only_by_its_owner(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    acme = db.company(ALICE.value, "greenhouse", "acme", name="Acme")

    async def attempt(user: UserId) -> tuple[bool, bool]:
        async with uow() as tx:
            changed = await tx.source_catalog.set_company_enabled(
                user,
                SourceId(acme),
                False,
            )
            deleted = await tx.source_catalog.delete_company(
                user,
                SourceId(acme),
            )
            await tx.commit()
            return changed is not None, deleted

    assert portal.call(attempt, BOB) == (False, False)
    assert db.rows("SELECT enabled FROM source_companies") == [(True,)]
    assert portal.call(attempt, ALICE) == (True, True)
    assert db.rows("SELECT enabled FROM source_companies") == []


def test_deleting_a_company_takes_its_run_state_with_it(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    acme = db.company(ALICE.value, "greenhouse", "acme", name="Acme")
    sub = Subscription(SourceId(acme), ALICE, Platform.GREENHOUSE, "acme", "Acme")

    async def go() -> None:
        async with uow() as tx:
            await tx.source_runs.save(sub, SourceRun(NOW))
            await tx.commit()
        async with uow() as tx:
            assert await tx.source_catalog.delete_company(ALICE, SourceId(acme))
            await tx.commit()

    portal.call(go)

    assert db.rows(COMPANY_RUNS) == []


def test_saving_the_state_of_a_deleted_source_says_it_is_gone(
    portal: BlockingPortal, uow: UnitOfWorkFactory, db: Db
) -> None:
    acme = db.company(ALICE.value, "greenhouse", "acme", name="Acme")
    sub = Subscription(SourceId(acme), ALICE, Platform.GREENHOUSE, "acme", "Acme")
    db.execute("DELETE FROM source_companies")

    async def save() -> BaseException | None:
        try:
            async with uow() as tx:
                await tx.source_runs.save(sub, SourceRun(NOW))
                await tx.commit()
        except Exception as exc:
            return exc
        return None

    raised = portal.call(save)

    assert isinstance(raised, SourceGone), repr(raised)
    assert db.rows(COMPANY_RUNS) == []
