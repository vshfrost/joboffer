"""Імпорт вакансій із джерела на справжньому Postgres: дедуп «компанія + посада» за вікном (і для схованих),
дописування тексту, фільтр за збереженим профілем, номери на користувача, `recent` у репозиторії."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.sources.imports import SourceImportUseCases
from domain.identity.email import Email
from domain.identity.ids import UserId
from domain.identity.password import PasswordHash
from domain.identity.user import DisplayName, User
from domain.jobs.ids import JobId
from domain.jobs.job import Job, NewJob
from domain.jobs.linkedin import linkedin_job_url
from domain.profile.locations import Locations, SearchLocation
from domain.profile.modes import WorkMode
from domain.profile.profile import Profile
from domain.profile.rules import Rules
from domain.sources.dedup import RecentJob
from domain.sources.importing import ImportSummary
from domain.sources.kinds import FeedSource, Platform
from domain.sources.posting import Posting
from infrastructure.db.unit_of_work import UnitOfWorkFactory, unit_of_work_factory
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds

NOW = datetime(2026, 1, 31, 9, 0, tzinfo=UTC)
ALICE = UserId(UUID(int=1))
BOB = UserId(UUID(int=2))


@pytest.fixture
def uow(portal: BlockingPortal, engine: AsyncEngine) -> UnitOfWorkFactory:
    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
        factory = unit_of_work_factory(engine)
        async with factory() as tx:
            for number, user_id in enumerate((ALICE, BOB), start=1):
                await tx.users.add(
                    User.register(
                        id=user_id,
                        email=Email(f"user{number}@example.com"),
                        display_name=DisplayName(f"User {number}"),
                        password_hash=PasswordHash("$test$"),
                        now=NOW,
                    )
                )
            await tx.commit()

    portal.call(prepare)
    return unit_of_work_factory(engine)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def imports(uow: UnitOfWorkFactory, clock: FakeClock) -> SourceImportUseCases:
    return SourceImportUseCases(uow, clock, SequentialIds(start=0x1000))


def posting(title: str = "Backend Engineer", **fields: object) -> Posting:
    base: dict[str, object] = {
        "title": title,
        "url": f"https://boards.example/{title.replace(' ', '-')}",
        "text": f"Description of {title}",
    }
    return Posting(**(base | fields))  # type: ignore[arg-type]


_seeded = iter(range(0xA000, 0xB000))


async def _add_job(
    uow: UnitOfWorkFactory,
    user_id: UserId,
    job: NewJob,
    now: datetime = NOW,
) -> int:
    async with uow() as tx:
        number = await tx.jobs.add(user_id, JobId(UUID(int=next(_seeded))), job, now)
        await tx.commit()
        return number


async def _get(uow: UnitOfWorkFactory, user_id: UserId, number: int) -> Job | None:
    async with uow() as tx:
        return await tx.jobs.get(user_id, number)


async def _recent(
    uow: UnitOfWorkFactory, user_id: UserId, since: datetime
) -> list[RecentJob]:
    async with uow() as tx:
        return await tx.jobs.recent(user_id, since)


async def _dismiss(uow: UnitOfWorkFactory, user_id: UserId, number: int) -> None:
    async with uow() as tx:
        await tx.jobs.dismiss(user_id, [number], "не цікаво", NOW)
        await tx.commit()


async def _save_profile(
    uow: UnitOfWorkFactory, user_id: UserId, profile: Profile
) -> None:
    async with uow() as tx:
        await tx.profiles.replace(user_id, profile, NOW)
        await tx.commit()


# --- репозиторій: недавні вакансії ----------------------------------------------------------


def test_recent_returns_jobs_added_since_the_moment_with_hidden_and_waiting_ones(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    since = NOW - timedelta(days=30)
    first = portal.call(
        _add_job, uow, ALICE, NewJob(text="a", title="Dev", company="Acme"), NOW
    )
    hidden = portal.call(
        _add_job, uow, ALICE, NewJob(text="b", title="Ops", company="Globex"), NOW
    )
    waiting = portal.call(
        _add_job,
        uow,
        ALICE,
        NewJob(text=None, title="QA", company="Initech", linkedin_id="4012345678"),
        NOW,
    )
    portal.call(_dismiss, uow, ALICE, hidden)
    found = portal.call(_recent, uow, ALICE, since)
    assert sorted(found, key=lambda job: job.number) == [
        RecentJob(first, "Acme", "Dev", False),
        RecentJob(hidden, "Globex", "Ops", False),
        RecentJob(waiting, "Initech", "QA", True),
    ]


def test_recent_skips_older_jobs_and_keeps_the_boundary(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    since = NOW - timedelta(days=30)
    portal.call(
        _add_job,
        uow,
        ALICE,
        NewJob(text="old", title="Old"),
        since - timedelta(seconds=1),
    )
    edge = portal.call(_add_job, uow, ALICE, NewJob(text="edge", title="Edge"), since)
    assert [job.number for job in portal.call(_recent, uow, ALICE, since)] == [edge]


def test_recent_holds_only_the_users_own_jobs(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add_job, uow, BOB, NewJob(text="bob", title="Bob job"), NOW)
    assert portal.call(_recent, uow, ALICE, NOW - timedelta(days=30)) == []


# --- імпорт ---------------------------------------------------------------------------------


def test_a_new_job_keeps_the_source_the_location_and_a_per_user_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory, imports: SourceImportUseCases
) -> None:
    mine = portal.call(
        imports.import_postings,
        ALICE,
        Platform.GREENHOUSE,
        [posting(locations=("Valencia", "Madrid"), work_mode=WorkMode.HYBRID)],
        "Acme",
    )
    bobs = portal.call(
        imports.import_postings, BOB, FeedSource.DOU, [posting(company="Globex")]
    )
    first = portal.call(_get, uow, ALICE, 1)
    second = portal.call(_get, uow, BOB, 1)
    assert (mine.imported, bobs.imported) == (1, 1)
    assert first is not None
    assert (first.source, first.company, first.location) == (
        "ats:greenhouse",
        "Acme",
        "Valencia; Madrid",
    )
    assert second is not None
    assert (second.source, second.company, second.location) == (
        "rss:dou",
        "Globex",
        None,
    )


def test_the_same_company_and_title_is_a_duplicate_even_for_a_hidden_job(
    portal: BlockingPortal, uow: UnitOfWorkFactory, imports: SourceImportUseCases
) -> None:
    hidden = portal.call(
        _add_job,
        uow,
        ALICE,
        NewJob(text="mine", title="Back-end Engineer", company="Acme S.L."),
    )
    portal.call(_dismiss, uow, ALICE, hidden)
    summary = portal.call(
        imports.import_postings,
        ALICE,
        Platform.ASHBY,
        [posting("BACK END engineer")],
        "ACME Inc.",
    )
    assert summary == ImportSummary(found=1, duplicate=1)


def test_a_waiting_linkedin_job_gets_the_text_and_keeps_its_own_fields(
    portal: BlockingPortal, uow: UnitOfWorkFactory, imports: SourceImportUseCases
) -> None:
    number = portal.call(
        _add_job,
        uow,
        ALICE,
        NewJob(
            text=None,
            url=linkedin_job_url("4012345678"),
            title="Backend Engineer",
            company="Acme Inc",
            linkedin_id="4012345678",
            source="linkedin_alert",
        ),
    )
    summary = portal.call(
        imports.import_postings,
        ALICE,
        Platform.LEVER,
        [posting(text="Full description")],
        "Acme",
    )
    saved = portal.call(_get, uow, ALICE, number)
    assert summary == ImportSummary(found=1, completed=1)
    assert saved is not None
    assert (saved.text, saved.title, saved.company, saved.url, saved.source) == (
        "Full description",
        "Backend Engineer",
        "Acme Inc",
        linkedin_job_url("4012345678"),
        "linkedin_alert",
    )


def test_a_job_older_than_30_days_does_not_make_a_duplicate(
    portal: BlockingPortal,
    uow: UnitOfWorkFactory,
    imports: SourceImportUseCases,
    clock: FakeClock,
) -> None:
    portal.call(
        _add_job,
        uow,
        ALICE,
        NewJob(text="old", title="Backend Engineer", company="Acme"),
        NOW - timedelta(days=31),
    )
    summary = portal.call(
        imports.import_postings, ALICE, Platform.GREENHOUSE, [posting()], "Acme"
    )
    assert summary == ImportSummary(found=1, imported=1)


def test_the_same_url_or_text_is_a_duplicate(
    portal: BlockingPortal, uow: UnitOfWorkFactory, imports: SourceImportUseCases
) -> None:
    portal.call(
        _add_job,
        uow,
        ALICE,
        NewJob(text="Same text", url="https://boards.example/1", title="Other"),
    )
    summary = portal.call(
        imports.import_postings,
        ALICE,
        Platform.GREENHOUSE,
        [
            posting("First", url="https://boards.example/1"),
            posting("Second", text="same TEXT"),
        ],
        "Acme",
    )
    assert summary == ImportSummary(found=2, duplicate=2)


def test_the_stored_profile_filters_the_import(
    portal: BlockingPortal, uow: UnitOfWorkFactory, imports: SourceImportUseCases
) -> None:
    profile = Profile(
        locations=Locations(
            locations=(
                SearchLocation("Valencia", ("Валенсія",), frozenset({WorkMode.HYBRID})),
            ),
            include_unknown_mode=False,
        ),
        rules=Rules(title_keywords=("backend",), title_exclude=("junior",)),
    )
    portal.call(_save_profile, uow, ALICE, profile)
    summary = portal.call(
        imports.import_postings,
        ALICE,
        Platform.GREENHOUSE,
        [
            posting(
                "Backend Engineer", locations=("Валенсія",), work_mode=WorkMode.HYBRID
            ),
            posting(
                "Junior Backend Engineer",
                locations=("Valencia",),
                work_mode=WorkMode.HYBRID,
            ),
            posting(
                "Frontend Engineer", locations=("Valencia",), work_mode=WorkMode.HYBRID
            ),
            posting("Platform Backend", locations=("Valencia",)),
            posting("Data Backend", locations=("Berlin",), work_mode=WorkMode.HYBRID),
        ],
        "Acme",
    )
    assert summary == ImportSummary(found=5, imported=1, filtered=4)
