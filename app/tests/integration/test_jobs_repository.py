"""PostgresJobs на справжній базі: номери на користувача, унікальності, дублі, список, приховування, схема для ETL."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.jobs import AddOutcome, JobInput
from application.jobs.use_cases import JobUseCases
from domain.identity.email import Email
from domain.identity.ids import UserId
from domain.identity.password import PasswordHash
from domain.identity.user import DisplayName, User
from domain.jobs.ids import JobId
from domain.jobs.job import Job, NewJob
from domain.jobs.search import JobSearch
from domain.shared.fingerprint import text_fingerprint
from infrastructure.db.unit_of_work import UnitOfWorkFactory, unit_of_work_factory
from infrastructure.system import RandomIds, SystemClock

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
ALICE = UserId(UUID(int=1))
BOB = UserId(UUID(int=2))

# Усі поля таблиці `jobs` v1 (крім ключів): ETL у B12 переносить їх без втрат.
V1_JOB_COLUMNS = {
    "source",
    "url",
    "title",
    "company",
    "text",
    "text_hash",
    "linkedin_id",
    "location",
    "created_at",
    "opened_at",
    "dismissed_at",
    "dismiss_reason",
}


def posting(body: str = "Senior Python engineer", **fields: str | None) -> NewJob:
    base: dict[str, str | None] = {
        "url": None,
        "title": None,
        "company": None,
        "linkedin_id": None,
        "location": None,
    }
    return NewJob(text=body, **(base | fields))  # type: ignore[arg-type]


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


async def _add(
    uow: UnitOfWorkFactory,
    user_id: UserId,
    job: NewJob,
    now: datetime = NOW,
    number: int | None = None,
) -> int:
    async with uow() as tx:
        added = await tx.jobs.add(
            user_id, JobId(UUID(int=0xA000 + _seq())), job, now, number
        )
        await tx.commit()
        return added


_counter = iter(range(1, 10_000))


def _seq() -> int:
    return next(_counter)


async def _get(uow: UnitOfWorkFactory, user_id: UserId, number: int) -> Job | None:
    async with uow() as tx:
        return await tx.jobs.get(user_id, number)


async def _search(
    uow: UnitOfWorkFactory, user_id: UserId, search: JobSearch | None = None
) -> list[int]:
    async with uow() as tx:
        found = await tx.jobs.search(user_id, search or JobSearch())
    return [item.number for item in found]


async def _scalar(engine: AsyncEngine, sql: str) -> object:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar()


def test_numbers_start_at_one_and_grow_per_user(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_add, uow, ALICE, posting("one"))
    second = portal.call(_add, uow, ALICE, posting("two"))
    bobs = portal.call(_add, uow, BOB, posting("one"))
    assert (first, second, bobs) == (1, 2, 1)


def test_an_explicit_number_is_kept_and_the_counter_continues_after_it(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    assert portal.call(_add, uow, ALICE, posting("v1 job"), NOW, 41) == 41
    assert portal.call(_add, uow, ALICE, posting("next")) == 42


def test_a_smaller_explicit_number_does_not_lower_the_counter(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("a"), NOW, 10)
    portal.call(_add, uow, ALICE, posting("b"), NOW, 3)
    assert portal.call(_add, uow, ALICE, posting("c")) == 11


def test_an_explicit_number_already_taken_is_rejected(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("a"), NOW, 5)
    with pytest.raises(IntegrityError):
        portal.call(_add, uow, ALICE, posting("b"), NOW, 5)


def test_a_rolled_back_addition_does_not_use_up_a_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def add_without_commit() -> None:
        async with uow() as tx:
            await tx.jobs.add(ALICE, JobId(UUID(int=0xB001)), posting("x"), NOW)

    portal.call(add_without_commit)
    assert portal.call(_add, uow, ALICE, posting("y")) == 1


def test_a_job_roundtrips_with_all_its_fields(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = posting(
        "Body",
        url="https://acme.com/1",
        title="Dev",
        company="Acme",
        linkedin_id="4012345678",
        location="Valencia",
    )
    number = portal.call(_add, uow, ALICE, job)
    saved = portal.call(_get, uow, ALICE, number)
    assert saved is not None
    assert (saved.number, saved.source, saved.text, saved.url, saved.title) == (
        1,
        "manual",
        "Body",
        "https://acme.com/1",
        "Dev",
    )
    assert (saved.company, saved.location, saved.created_at) == (
        "Acme",
        "Valencia",
        NOW,
    )
    assert (saved.dismissed_at, saved.dismiss_reason, saved.needs_text) == (
        None,
        None,
        False,
    )


def test_the_source_is_stored(portal: BlockingPortal, uow: UnitOfWorkFactory) -> None:
    number = portal.call(
        _add, uow, ALICE, NewJob(text=None, title="Dev", source="linkedin_alert")
    )
    saved = portal.call(_get, uow, ALICE, number)
    assert saved is not None
    assert (saved.source, saved.text, saved.needs_text) == (
        "linkedin_alert",
        None,
        True,
    )


def test_a_job_of_another_user_or_a_missing_one_is_none(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(_add, uow, ALICE, posting())
    assert portal.call(_get, uow, BOB, number) is None
    assert portal.call(_get, uow, ALICE, 99) is None
    assert portal.call(_get, uow, ALICE, 2**40) is None


async def _duplicate(
    uow: UnitOfWorkFactory, user_id: UserId, job: NewJob
) -> int | None:
    async with uow() as tx:
        return await tx.jobs.find_duplicate(user_id, job)


def test_a_duplicate_is_found_by_text_url_or_linkedin_id(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(
        _add,
        uow,
        ALICE,
        posting("Body", url="https://acme.com/1", linkedin_id="4012345678"),
    )
    assert portal.call(_duplicate, uow, ALICE, NewJob(text="  BODY ")) == number
    assert (
        portal.call(_duplicate, uow, ALICE, NewJob(text="x", url="https://acme.com/1"))
        == number
    )
    assert (
        portal.call(_duplicate, uow, ALICE, NewJob(text="x", linkedin_id="4012345678"))
        == number
    )
    assert (
        portal.call(_duplicate, uow, ALICE, NewJob(text="x", url="https://acme.com/2"))
        is None
    )


def test_a_duplicate_is_never_found_across_users(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("Body", url="https://acme.com/1"))
    assert (
        portal.call(_duplicate, uow, BOB, posting("Body", url="https://acme.com/1"))
        is None
    )


def test_missing_values_duplicate_nothing(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, NewJob(text=None, title="A", source="linkedin_alert"))
    portal.call(_add, uow, ALICE, NewJob(text=None, title="B", source="linkedin_alert"))
    assert portal.call(_duplicate, uow, ALICE, NewJob(text=None)) is None
    assert portal.call(_duplicate, uow, ALICE, NewJob(text="anything")) is None


def test_the_oldest_of_several_duplicates_is_returned(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_add, uow, ALICE, posting("same body", url="https://a.com/1"))
    portal.call(_add, uow, ALICE, posting("other", url="https://a.com/2"))
    found = portal.call(
        _duplicate, uow, ALICE, NewJob(text="same body", url="https://a.com/2")
    )
    assert found == first


async def _find_linkedin(
    uow: UnitOfWorkFactory, user_id: UserId, id_: str
) -> int | None:
    async with uow() as tx:
        return await tx.jobs.find_linkedin(user_id, id_)


def test_a_linkedin_job_is_found_by_id_or_by_its_canonical_url(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    by_id = portal.call(_add, uow, ALICE, NewJob(text=None, linkedin_id="4012345678"))
    by_url = portal.call(
        _add,
        uow,
        ALICE,
        NewJob(text=None, url="https://www.linkedin.com/jobs/view/4099999999"),
    )
    assert portal.call(_find_linkedin, uow, ALICE, "4012345678") == by_id
    assert portal.call(_find_linkedin, uow, ALICE, "4099999999") == by_url
    assert portal.call(_find_linkedin, uow, ALICE, "4000000000") is None
    assert portal.call(_find_linkedin, uow, BOB, "4012345678") is None


@pytest.mark.parametrize(
    "second",
    [
        pytest.param(posting("same", url="https://a.com/2"), id="text"),
        pytest.param(posting("other", url="https://a.com/1"), id="url"),
        pytest.param(posting("other", linkedin_id="4012345678"), id="linkedin"),
    ],
)
def test_the_database_refuses_a_second_job_with_the_same_text_url_or_linkedin_id(
    portal: BlockingPortal, uow: UnitOfWorkFactory, second: NewJob
) -> None:
    first = posting("same", url="https://a.com/1", linkedin_id="4012345678")
    portal.call(_add, uow, ALICE, first)
    with pytest.raises(IntegrityError):
        portal.call(_add, uow, ALICE, second)


def test_another_user_may_have_the_same_text_url_and_linkedin_id(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = posting("same", url="https://a.com/1", linkedin_id="4012345678")
    portal.call(_add, uow, ALICE, job)
    assert portal.call(_add, uow, BOB, job) == 1


def test_the_text_of_a_waiting_job_is_completed_once(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(
        _add, uow, ALICE, NewJob(text=None, title="Dev", linkedin_id="4012345678")
    )

    async def complete(body: str) -> None:
        async with uow() as tx:
            await tx.jobs.complete_text(ALICE, number, body)
            await tx.commit()

    portal.call(complete, "First description")
    portal.call(complete, "Second description")
    saved = portal.call(_get, uow, ALICE, number)
    assert saved is not None
    assert (saved.text, saved.title, saved.needs_text) == (
        "First description",
        "Dev",
        False,
    )
    assert (
        portal.call(_duplicate, uow, ALICE, NewJob(text="first DESCRIPTION")) == number
    )


def test_the_list_is_newest_first_with_waiting_jobs_last(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    old = portal.call(_add, uow, ALICE, posting("old"), NOW)
    waiting = portal.call(
        _add, uow, ALICE, NewJob(text=None, title="W"), NOW + timedelta(days=5)
    )
    new = portal.call(_add, uow, ALICE, posting("new"), NOW + timedelta(days=1))
    same_time = portal.call(
        _add, uow, ALICE, posting("same time"), NOW + timedelta(days=1)
    )
    assert portal.call(_search, uow, ALICE) == [same_time, new, old, waiting]


def test_the_list_filters(portal: BlockingPortal, uow: UnitOfWorkFactory) -> None:
    rust = portal.call(_add, uow, ALICE, posting("we like Rust", title="Engineer"), NOW)
    titled = portal.call(_add, uow, ALICE, posting("b", title="rust dev"), NOW)
    company = portal.call(_add, uow, ALICE, posting("c", company="Rustacean"), NOW)
    waiting = portal.call(
        _add, uow, ALICE, NewJob(text=None, title="Go", source="linkedin_alert"), NOW
    )
    fresh = portal.call(_add, uow, ALICE, posting("fresh"), NOW + timedelta(days=9))

    def found(**fields: object) -> list[int]:
        search = JobSearch(**fields)  # type: ignore[arg-type]
        return sorted(portal.call(_search, uow, ALICE, search))

    assert found(query="RUST") == sorted([rust, titled, company])
    assert found(source="linkedin_alert") == [waiting]
    assert found(needs_text=True) == [waiting]
    assert found(since=NOW + timedelta(days=5)) == [fresh]
    assert found(limit=2) == sorted([fresh, company])


def test_the_query_is_matched_literally(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    percent = portal.call(_add, uow, ALICE, posting("100% remote"))
    portal.call(_add, uow, ALICE, posting("1000 remote"))
    underscore = portal.call(_add, uow, ALICE, posting("snake_case lover"))
    portal.call(_add, uow, ALICE, posting("snakeXcase lover"))
    backslash = portal.call(_add, uow, ALICE, posting(r"path C:\temp"))
    assert portal.call(_search, uow, ALICE, JobSearch(query="100%")) == [percent]
    assert portal.call(_search, uow, ALICE, JobSearch(query="snake_case")) == [
        underscore
    ]
    assert portal.call(_search, uow, ALICE, JobSearch(query="\\temp")) == [backslash]


def test_the_list_holds_only_own_jobs_and_sources(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("a"))
    portal.call(_add, uow, ALICE, NewJob(text=None, source="linkedin_alert"))
    portal.call(_add, uow, BOB, NewJob(text="b", source="greenhouse"))

    async def sources(user_id: UserId) -> list[str]:
        async with uow() as tx:
            return await tx.jobs.sources(user_id)

    assert portal.call(sources, ALICE) == ["linkedin_alert", "manual"]
    assert portal.call(sources, BOB) == ["greenhouse"]
    assert len(portal.call(_search, uow, BOB)) == 1


def test_dismissing_hides_from_the_list_and_keeps_the_first_reason(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    kept = portal.call(_add, uow, ALICE, posting("kept"))
    gone = portal.call(_add, uow, ALICE, posting("gone"))

    async def dismiss(reason: str, at: datetime) -> None:
        async with uow() as tx:
            await tx.jobs.dismiss(ALICE, [gone], reason, at)
            await tx.commit()

    portal.call(dismiss, "перша", NOW)
    portal.call(dismiss, "друга", NOW + timedelta(hours=1))
    assert portal.call(_search, uow, ALICE) == [kept]
    assert portal.call(_search, uow, ALICE, JobSearch(dismissed=True)) == [gone]
    saved = portal.call(_get, uow, ALICE, gone)
    assert saved is not None
    assert (saved.dismissed_at, saved.dismiss_reason) == (NOW, "перша")


def test_dismissing_does_not_touch_another_users_job(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    number = portal.call(_add, uow, ALICE, posting("a"))

    async def dismiss_as_bob() -> None:
        async with uow() as tx:
            await tx.jobs.dismiss(BOB, [number], "x", NOW)
            await tx.commit()

    portal.call(dismiss_as_bob)
    assert portal.call(_search, uow, ALICE) == [number]


def test_restoring_returns_the_job_and_leaves_others_alone(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    hidden = portal.call(_add, uow, ALICE, posting("hidden"))
    plain = portal.call(_add, uow, ALICE, posting("plain"))

    async def run() -> None:
        async with uow() as tx:
            await tx.jobs.dismiss(ALICE, [hidden], "x", NOW)
            await tx.jobs.restore(ALICE, hidden)
            await tx.jobs.restore(ALICE, plain)
            await tx.commit()

    portal.call(run)
    assert sorted(portal.call(_search, uow, ALICE)) == [hidden, plain]
    saved = portal.call(_get, uow, ALICE, hidden)
    assert saved is not None
    assert (saved.dismissed_at, saved.dismiss_reason) == (None, None)


def test_parallel_additions_of_the_same_text_create_one_job(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    use_cases = JobUseCases(uow, SystemClock(), RandomIds())
    actor = Actor(
        user_id=ALICE,
        channel=Channel.WEB,
        client_id="web",
        grant_id=None,
        scopes=frozenset(Scope),
        correlation_id="test",
    )

    async def race() -> list[tuple[int, AddOutcome]]:
        results = await asyncio.gather(
            *(use_cases.add_job(actor, JobInput(text="Same posting")) for _ in range(8))
        )
        return [(item.job_number, item.outcome) for item in results]

    results = portal.call(race)
    assert sorted(outcome for _, outcome in results).count(AddOutcome.CREATED) == 1
    assert {number for number, _ in results} == {1}
    assert len(portal.call(_search, uow, ALICE)) == 1


def test_the_job_table_has_every_column_of_v1(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    async def columns() -> set[str]:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'jobs'"
                )
            )
            return {row[0] for row in rows}

    assert portal.call(columns) >= V1_JOB_COLUMNS


def test_the_stored_hash_is_the_text_fingerprint(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE, posting("Some  Body"))
    assert portal.call(
        _scalar, engine, "SELECT text_hash FROM jobs"
    ) == text_fingerprint("some body")


def test_removing_a_user_removes_the_jobs_and_the_counter(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE, posting("a"))

    async def delete_alice() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM users WHERE id = :id"), {"id": ALICE.value}
            )

    portal.call(delete_alice)
    assert portal.call(_scalar, engine, "SELECT count(*) FROM jobs") == 0
    assert portal.call(_scalar, engine, "SELECT count(*) FROM job_counters") == 0


def test_a_number_below_one_is_refused(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    with pytest.raises(IntegrityError):
        portal.call(_add, uow, ALICE, posting("a"), NOW, 0)
