"""Версія CV подачі на справжній базі: пишеться разом із подачею, живе й гине з нею, а рядок
без версії (подача до цієї можливості чи без CV) читається як «невідомо»."""

from datetime import UTC, date, datetime
from uuid import UUID

from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.applications.use_cases import ApplicationUseCases
from application.contracts.actor import Actor, Channel, Scope
from application.contracts.applications import ApplicationInput, CvVersionData
from domain.applications.application import (
    Application,
    ApplicationChannel,
    CvVersion,
    NewApplication,
)
from domain.documents.ids import DocumentId
from domain.documents.lint import KeywordCoverage, LintReport
from domain.identity.ids import UserId
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_applications_repository import details
from tests.integration.test_documents_repository import CV
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, _add, posting, uow
from tests.support.clock import FakeClock

__all__ = ["uow"]

VERSION = CvVersion(number=7, saved_on=date(2026, 1, 5), coverage_percent=83)


async def _save(
    uow: UnitOfWorkFactory, user: UserId, number: int, new: NewApplication
) -> Application:
    async with uow() as tx:
        saved = await tx.applications.save(user, number, new, NOW)
        await tx.commit()
        return saved


async def _get(uow: UnitOfWorkFactory, user: UserId, number: int) -> Application | None:
    async with uow() as tx:
        return await tx.applications.get(user, number)


async def _all(uow: UnitOfWorkFactory, user: UserId) -> list[Application]:
    async with uow() as tx:
        return await tx.applications.list_all(user)


async def _scalar(engine: AsyncEngine, sql: str) -> object:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar()


async def _run(engine: AsyncEngine, sql: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql))


def test_a_version_saved_with_the_application_is_read_back(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))

    saved = portal.call(_save, uow, ALICE, 1, details(cv=VERSION))

    assert saved.cv == VERSION
    read = portal.call(_get, uow, ALICE, 1)
    assert read is not None
    assert read.cv == VERSION


def test_saving_the_application_again_replaces_or_forgets_the_version(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_save, uow, ALICE, 1, details(cv=VERSION))
    newer = CvVersion(number=9, saved_on=date(2026, 1, 8), coverage_percent=None)

    portal.call(_save, uow, ALICE, 1, details(cv=newer))
    read = portal.call(_get, uow, ALICE, 1)
    assert read is not None
    assert read.cv == newer

    portal.call(_save, uow, ALICE, 1, details())
    read = portal.call(_get, uow, ALICE, 1)
    assert read is not None
    assert read.cv is None


def test_an_application_row_from_before_versions_reads_as_unknown(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(
        _run,
        engine,
        "INSERT INTO applications (job_id, user_id, status, applied_on, channel, "
        "status_changed_at) SELECT id, user_id, 'applied', '2026-01-01', 'email', now() "
        "FROM jobs",
    )

    read = portal.call(_get, uow, ALICE, 1)

    assert read is not None
    assert (read.channel, read.cv) == (ApplicationChannel.EMAIL, None)


def test_deleting_the_job_deletes_the_version_with_its_application(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_save, uow, ALICE, 1, details(cv=VERSION))

    portal.call(_run, engine, "DELETE FROM jobs")

    assert (
        portal.call(_scalar, engine, "SELECT count(*) FROM application_cv_versions")
        == 0
    )


def test_listing_gives_only_my_applications_in_job_order_with_their_versions(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    for body in ("one", "two"):
        portal.call(_add, uow, ALICE, posting(body))
    portal.call(_add, uow, BOB, posting("theirs"))
    portal.call(_save, uow, ALICE, 2, details(cv=VERSION))
    portal.call(_save, uow, ALICE, 1, details())
    portal.call(_save, uow, BOB, 1, details(cv=VERSION))

    mine = portal.call(_all, uow, ALICE)

    assert [(item.job_number, item.cv) for item in mine] == [(1, None), (2, VERSION)]


def test_marking_applied_records_the_latest_cv_of_the_job_on_the_database(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))

    async def save_cv() -> None:
        async with uow() as tx:
            job = await tx.jobs.get(ALICE, 1)
            assert job is not None
            await tx.documents.add(
                ALICE,
                DocumentId(UUID(int=0xE001)),
                job.id,
                CV,
                NOW,
                lint=LintReport(
                    pages=1, keywords=KeywordCoverage(("Payments",), ("Kafka",))
                ),
            )
            await tx.commit()

    portal.call(save_cv)
    clock = FakeClock(datetime(2026, 1, 9, 12, 0, tzinfo=UTC))
    actor = Actor(
        user_id=ALICE,
        channel=Channel.WEB,
        client_id="web",
        grant_id=None,
        scopes=frozenset(Scope),
        correlation_id="test",
    )

    saved = portal.call(
        ApplicationUseCases(uow, clock).mark_applied,
        actor,
        1,
        ApplicationInput(channel="email"),
    )

    assert saved.cv == CvVersionData(
        number=1, saved_on=date(2026, 1, 1), coverage_percent=50
    )
