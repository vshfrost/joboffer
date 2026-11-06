"""PostgresApplications на справжній базі: одна подача на вакансію, деталі й статус окремо, ізоляція, схема для ETL."""

from datetime import UTC, date, datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from application.applications.use_cases import ApplicationUseCases
from application.contracts.actor import Actor, Channel, Scope
from application.contracts.applications import ApplicationInput
from application.jobs.use_cases import JobUseCases
from domain.applications.application import (
    Application,
    ApplicationChannel,
    ApplicationStatus,
    AtsPlatform,
    NewApplication,
)
from domain.applications.errors import JobHasApplication
from domain.identity.ids import UserId
from domain.jobs.search import JobSearch
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from infrastructure.system import RandomIds
from tests.integration.test_jobs_repository import (
    ALICE,
    BOB,
    NOW,
    _add,
    posting,
    uow,
)
from tests.support.clock import FakeClock

__all__ = ["uow"]

S = ApplicationStatus
LATER = NOW + timedelta(days=3)

# Усі поля таблиці `applications` v1 (крім ключів): ETL у B12 переносить їх без втрат.
V1_APPLICATION_COLUMNS = {
    "status",
    "applied_on",
    "channel",
    "ats",
    "company_domains",
    "company_emails",
    "status_changed_at",
    "created_at",
    "updated_at",
}


def details(**fields: object) -> NewApplication:
    base: dict[str, object] = {
        "applied_on": date(2026, 1, 1),
        "channel": ApplicationChannel.EMAIL,
    }
    return NewApplication(**(base | fields))  # type: ignore[arg-type]


async def _save(
    uow: UnitOfWorkFactory,
    user_id: UserId,
    number: int,
    new: NewApplication,
    now: datetime = NOW,
) -> Application:
    async with uow() as tx:
        saved = await tx.applications.save(user_id, number, new, now)
        await tx.commit()
        return saved


async def _move(
    uow: UnitOfWorkFactory,
    user_id: UserId,
    number: int,
    status: ApplicationStatus,
    now: datetime = LATER,
) -> Application:
    async with uow() as tx:
        moved = await tx.applications.set_status(user_id, number, status, now)
        await tx.commit()
        return moved


async def _get(
    uow: UnitOfWorkFactory, user_id: UserId, number: int
) -> Application | None:
    async with uow() as tx:
        return await tx.applications.get(user_id, number)


async def _rows(engine: AsyncEngine, sql: str) -> list[tuple[object, ...]]:
    async with engine.connect() as conn:
        return [tuple(row) for row in (await conn.execute(text(sql))).all()]


def test_a_new_application_is_applied_with_all_its_details(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    saved = portal.call(
        _save,
        uow,
        ALICE,
        1,
        details(
            ats=AtsPlatform.GREENHOUSE,
            company_domains=("acme.com", "jobs.acme.com"),
            company_emails=("hr@acme.com",),
        ),
    )
    assert saved == Application(
        job_number=1,
        status=S.APPLIED,
        applied_on=date(2026, 1, 1),
        channel=ApplicationChannel.EMAIL,
        ats=AtsPlatform.GREENHOUSE,
        company_domains=("acme.com", "jobs.acme.com"),
        company_emails=("hr@acme.com",),
        status_changed_at=NOW,
    )
    assert portal.call(_get, uow, ALICE, 1) == saved


def test_the_details_without_ats_and_contacts_roundtrip_empty(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_save, uow, ALICE, 1, details())
    stored = portal.call(_get, uow, ALICE, 1)
    assert stored is not None
    assert (stored.ats, stored.company_domains, stored.company_emails) == (None, (), ())


@pytest.mark.parametrize("number", [0, -1, 2**31])
def test_a_job_number_outside_the_range_has_no_application(
    portal: BlockingPortal, uow: UnitOfWorkFactory, number: int
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_save, uow, ALICE, 1, details())
    assert portal.call(_get, uow, ALICE, number) is None


def test_a_job_without_application_has_none(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    assert portal.call(_get, uow, ALICE, 1) is None
    assert portal.call(_get, uow, ALICE, 99) is None


def test_saving_again_replaces_the_details_and_keeps_the_status_and_its_time(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_save, uow, ALICE, 1, details())
    portal.call(_move, uow, ALICE, 1, S.INTERVIEW)
    again = portal.call(
        _save,
        uow,
        ALICE,
        1,
        details(
            applied_on=date(2025, 12, 20),
            channel=ApplicationChannel.REFERRAL,
            company_domains=("acme.com",),
        ),
        LATER + timedelta(days=1),
    )
    assert again.status is S.INTERVIEW
    assert again.status_changed_at == LATER
    assert (again.applied_on, again.channel, again.ats, again.company_domains) == (
        date(2025, 12, 20),
        ApplicationChannel.REFERRAL,
        None,
        ("acme.com",),
    )
    assert portal.call(_get, uow, ALICE, 1) == again


def test_a_status_change_stores_the_status_and_its_time_only(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    first = portal.call(_save, uow, ALICE, 1, details(ats=AtsPlatform.LEVER))
    moved = portal.call(_move, uow, ALICE, 1, S.OFFER)
    assert moved.status is S.OFFER
    assert moved.status_changed_at == LATER
    assert moved.ats is AtsPlatform.LEVER
    assert (moved.applied_on, moved.channel) == (first.applied_on, first.channel)


def test_a_job_that_does_not_exist_cannot_get_an_application(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    with pytest.raises(LookupError):
        portal.call(_save, uow, ALICE, 7, details())


def test_a_status_cannot_be_set_where_there_is_no_application(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    with pytest.raises(LookupError):
        portal.call(_move, uow, ALICE, 1, S.REPLIED)


def test_the_same_number_of_two_users_holds_two_applications(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_add, uow, BOB, posting("one"))
    portal.call(_save, uow, ALICE, 1, details(channel=ApplicationChannel.ATS))
    portal.call(_save, uow, BOB, 1, details(channel=ApplicationChannel.LINKEDIN))
    portal.call(_move, uow, BOB, 1, S.REJECTED)
    alice = portal.call(_get, uow, ALICE, 1)
    bob = portal.call(_get, uow, BOB, 1)
    assert alice is not None
    assert bob is not None
    assert (alice.channel, alice.status) == (ApplicationChannel.ATS, S.APPLIED)
    assert (bob.channel, bob.status) == (ApplicationChannel.LINKEDIN, S.REJECTED)


def test_a_user_cannot_touch_the_application_of_another(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_save, uow, ALICE, 1, details())
    assert portal.call(_get, uow, BOB, 1) is None
    with pytest.raises(LookupError):
        portal.call(_save, uow, BOB, 1, details())
    with pytest.raises(LookupError):
        portal.call(_move, uow, BOB, 1, S.OFFER)


def test_deleting_the_job_deletes_its_application(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_save, uow, ALICE, 1, details())

    async def delete() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM jobs"))

    portal.call(delete)
    assert portal.call(_rows, engine, "SELECT 1 FROM applications") == []


def test_deleting_the_user_deletes_the_application(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_save, uow, ALICE, 1, details())

    async def delete() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM users"))

    portal.call(delete)
    assert portal.call(_rows, engine, "SELECT 1 FROM applications") == []


def test_there_is_one_application_per_job_at_most(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_save, uow, ALICE, 1, details())
    portal.call(_save, uow, ALICE, 1, details(channel=ApplicationChannel.ATS))
    assert portal.call(_rows, engine, "SELECT count(*) FROM applications") == [(1,)]


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE applications SET status = 'hired'",
        "UPDATE applications SET channel = 'phone'",
        "UPDATE applications SET ats = 'workday'",
    ],
)
def test_the_database_refuses_values_outside_the_v1_enums(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory, statement: str
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_save, uow, ALICE, 1, details())

    async def corrupt() -> None:
        async with engine.begin() as conn:
            await conn.execute(text(statement))

    with pytest.raises(IntegrityError):
        portal.call(corrupt)


def test_the_table_has_every_v1_column_for_the_etl(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    columns = portal.call(
        _rows,
        engine,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'applications'",
    )
    names = {name for (name,) in columns}
    assert names == V1_APPLICATION_COLUMNS | {"job_id", "user_id"}


# --- список ---


async def _status_of_all(uow: UnitOfWorkFactory, user_id: UserId) -> dict[int, object]:
    async with uow() as tx:
        found = await tx.jobs.search(user_id, JobSearch())
    return {item.number: item.status for item in found}


async def _numbers(
    uow: UnitOfWorkFactory, user_id: UserId, statuses: frozenset[ApplicationStatus]
) -> list[int]:
    async with uow() as tx:
        found = await tx.jobs.search(user_id, JobSearch(statuses=statuses))
    return [item.number for item in found]


def test_the_list_row_carries_the_status_of_the_application(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    for body in ("one", "two", "three"):
        portal.call(_add, uow, ALICE, posting(body))
    portal.call(_save, uow, ALICE, 2, details())
    portal.call(_save, uow, ALICE, 3, details())
    portal.call(_move, uow, ALICE, 3, S.OFFER)
    assert portal.call(_status_of_all, uow, ALICE) == {
        1: None,
        2: S.APPLIED,
        3: S.OFFER,
    }


def test_the_list_is_filtered_by_a_set_of_statuses(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    for number, body in enumerate(("a", "b", "c", "d"), start=1):
        portal.call(_add, uow, ALICE, posting(body), NOW + timedelta(minutes=number))
    for number in (1, 2, 3):
        portal.call(_save, uow, ALICE, number, details())
    portal.call(_move, uow, ALICE, 2, S.REPLIED)
    portal.call(_move, uow, ALICE, 3, S.REJECTED)
    active = frozenset({S.APPLIED, S.REPLIED})
    assert portal.call(_numbers, uow, ALICE, active) == [2, 1]
    assert portal.call(_numbers, uow, ALICE, frozenset({S.REJECTED})) == [3]
    assert portal.call(_numbers, uow, ALICE, frozenset({S.OFFER})) == []


def test_the_status_filter_does_not_see_the_applications_of_another_user(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_add, uow, BOB, posting("one"))
    portal.call(_save, uow, BOB, 1, details())
    assert portal.call(_numbers, uow, ALICE, frozenset(S)) == []
    assert portal.call(_numbers, uow, BOB, frozenset(S)) == [1]


# --- use cases на справжній базі ---


def _actor(user_id: UserId) -> Actor:
    return Actor(
        user_id=user_id,
        channel=Channel.WEB,
        client_id="web",
        grant_id=None,
        scopes=frozenset(Scope),
        correlation_id="test",
    )


def test_marking_applied_and_moving_work_end_to_end(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    clock = FakeClock(datetime(2026, 3, 1, 23, 30, tzinfo=UTC))
    applications = ApplicationUseCases(uow, clock)
    portal.call(_add, uow, ALICE, posting("one"))
    saved = portal.call(
        applications.mark_applied, _actor(ALICE), 1, ApplicationInput(channel="email")
    )
    assert (saved.status, saved.applied_on) == (S.APPLIED, date(2026, 3, 2))
    moved = portal.call(
        applications.set_application_status, _actor(ALICE), 1, "interview"
    )
    assert moved.allowed_transitions == (S.OFFER, S.REJECTED, S.WITHDRAWN)
    assert portal.call(applications.get_application, _actor(ALICE), 1) == moved


def test_an_applied_job_cannot_be_hidden_on_the_database(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    jobs = JobUseCases(uow, FakeClock(), RandomIds())
    portal.call(_add, uow, ALICE, posting("one"))
    portal.call(_add, uow, ALICE, posting("two"))
    portal.call(_save, uow, ALICE, 2, details())
    with pytest.raises(JobHasApplication) as caught:
        portal.call(jobs.dismiss_jobs, _actor(ALICE), [1, 2], "не цікаво")
    assert caught.value.message == (
        "Елемент 2: на вакансію 2 уже є подача — поданих вакансій не ховають."
    )
    assert sorted(portal.call(_status_of_all, uow, ALICE)) == [1, 2]
