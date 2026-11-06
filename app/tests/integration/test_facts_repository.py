"""Факти на справжній базі: номери на користувача, унікальності, дублі, каскад, схема для ETL."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.facts import FactInput
from application.facts.use_cases import FactUseCases
from domain.facts.fact import Fact, FactKind, FactSource, NewFact, NewOriginalCv
from domain.facts.ids import FactId
from domain.identity.email import Email
from domain.identity.ids import UserId
from domain.identity.password import PasswordHash
from domain.identity.user import DisplayName, User
from infrastructure.db.unit_of_work import UnitOfWorkFactory, unit_of_work_factory
from infrastructure.system import RandomIds, SystemClock

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
ALICE = UserId(UUID(int=1))
BOB = UserId(UUID(int=2))

# Усі поля таблиці `facts` v1 (крім ключів): ETL у B12 переносить їх без втрат.
V1_FACT_COLUMNS = {"kind", "text", "text_hash", "confirmed", "created_at", "updated_at"}


def skill(body: str = "Python", kind: FactKind = FactKind.SKILL) -> NewFact:
    return NewFact(kind, body)


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


_counter = iter(range(1, 10_000))


async def _add(
    uow: UnitOfWorkFactory,
    user_id: UserId,
    fact: NewFact,
    now: datetime = NOW,
    number: int | None = None,
) -> Fact:
    async with uow() as tx:
        added = await tx.facts.add(
            user_id, FactId(UUID(int=0xB000 + next(_counter))), fact, now, number
        )
        await tx.commit()
        return added


async def _all(uow: UnitOfWorkFactory, user_id: UserId) -> list[Fact]:
    async with uow() as tx:
        return await tx.facts.all(user_id)


async def _scalar(engine: AsyncEngine, sql: str) -> object:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar()


def test_numbers_start_at_one_and_grow_per_user(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_add, uow, ALICE, skill("one"))
    second = portal.call(_add, uow, ALICE, skill("two"))
    bobs = portal.call(_add, uow, BOB, skill("one"))
    assert (first.number, second.number, bobs.number) == (1, 2, 1)


def test_a_new_fact_is_unconfirmed_and_keeps_its_fields(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    added = portal.call(_add, uow, ALICE, skill("Python", FactKind.PROJECT))
    (stored,) = portal.call(_all, uow, ALICE)
    assert stored == added
    assert (stored.kind, stored.text, stored.confirmed) == (
        FactKind.PROJECT,
        "Python",
        False,
    )
    assert (stored.created_at, stored.updated_at) == (NOW, NOW)


def test_an_explicit_number_is_kept_and_the_counter_continues_after_it(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    assert portal.call(_add, uow, ALICE, skill("v1"), NOW, 41).number == 41
    assert portal.call(_add, uow, ALICE, skill("next")).number == 42


def test_a_smaller_explicit_number_does_not_lower_the_counter(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, skill("a"), NOW, 10)
    portal.call(_add, uow, ALICE, skill("b"), NOW, 3)
    assert portal.call(_add, uow, ALICE, skill("c")).number == 11


def test_a_deleted_number_is_not_reused(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, skill("a"))
    portal.call(_add, uow, ALICE, skill("b"))

    async def delete() -> None:
        async with uow() as tx:
            await tx.facts.delete(ALICE, 2)
            await tx.commit()

    portal.call(delete)
    assert portal.call(_add, uow, ALICE, skill("c")).number == 3


def test_a_rolled_back_transaction_does_not_spend_a_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def abandoned() -> None:
        async with uow() as tx:
            await tx.facts.add(ALICE, FactId(UUID(int=0xC001)), skill("x"), NOW)

    portal.call(abandoned)
    assert portal.call(_add, uow, ALICE, skill("y")).number == 1


def test_the_same_text_cannot_be_stored_twice_for_a_user(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, skill("Python"))
    with pytest.raises(IntegrityError):
        portal.call(_add, uow, ALICE, skill(" python ", FactKind.EXPERIENCE))
    assert portal.call(_add, uow, BOB, skill("Python")).number == 1


def test_find_duplicate_matches_by_fingerprint_for_the_same_user_only(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, skill("Python 3.14"))

    async def find(user: UserId, body: str) -> int | None:
        async with uow() as tx:
            return await tx.facts.find_duplicate(user, skill(body).fingerprint)

    assert portal.call(find, ALICE, "  python   3.14 ") == 1
    assert portal.call(find, ALICE, "Go") is None
    assert portal.call(find, BOB, "Python 3.14") is None


def test_get_is_scoped_to_the_user_and_ignores_out_of_range_numbers(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, skill("a"))

    async def get(user: UserId, number: int) -> Fact | None:
        async with uow() as tx:
            return await tx.facts.get(user, number)

    assert portal.call(get, ALICE, 1) is not None
    assert portal.call(get, BOB, 1) is None
    assert portal.call(get, ALICE, 0) is None
    assert portal.call(get, ALICE, 2**40) is None


def test_replace_changes_kind_and_text_and_drops_the_confirmation(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, skill("a"))
    later = NOW + timedelta(hours=1)

    async def run() -> Fact:
        async with uow() as tx:
            await tx.facts.confirm(ALICE, [1], NOW)
            await tx.facts.replace(ALICE, 1, skill("b", FactKind.LANGUAGE), later)
            await tx.commit()
        return (await _all(uow, ALICE))[0]

    changed = portal.call(run)
    assert (changed.kind, changed.text, changed.confirmed) == (
        FactKind.LANGUAGE,
        "b",
        False,
    )
    assert (changed.created_at, changed.updated_at) == (NOW, later)


def test_confirm_marks_only_the_users_given_numbers(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, skill("a"))
    portal.call(_add, uow, ALICE, skill("b"))
    portal.call(_add, uow, BOB, skill("a"))

    async def run() -> None:
        async with uow() as tx:
            await tx.facts.confirm(ALICE, [2], NOW)
            await tx.commit()

    portal.call(run)
    assert [f.confirmed for f in portal.call(_all, uow, ALICE)] == [False, True]
    assert [f.confirmed for f in portal.call(_all, uow, BOB)] == [False]


def test_the_original_cv_is_one_row_per_user_and_replaced(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[object, object, object]:
        async with uow() as tx:
            first = await tx.original_cvs.get(ALICE)
            await tx.original_cvs.save(ALICE, NewOriginalCv("old", "old.pdf"), NOW)
            await tx.original_cvs.save(
                ALICE, NewOriginalCv("new", None), NOW + timedelta(days=1)
            )
            await tx.commit()
        async with uow() as tx:
            return (
                first,
                await tx.original_cvs.get(ALICE),
                await tx.original_cvs.get(BOB),
            )

    first, mine, bobs = portal.call(run)
    assert first is None
    assert bobs is None
    assert (mine.text, mine.file_name, mine.saved_at) == (  # type: ignore[attr-defined]
        "new",
        None,
        NOW + timedelta(days=1),
    )


def test_deleting_a_user_removes_the_facts_counter_and_cv(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE, skill("a"))

    async def run() -> None:
        async with uow() as tx:
            await tx.original_cvs.save(ALICE, NewOriginalCv("cv", None), NOW)
            await tx.commit()
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM users WHERE id = :id"), {"id": ALICE.value}
            )

    portal.call(run)
    for count in (
        "SELECT count(*) FROM facts",
        "SELECT count(*) FROM fact_counters",
        "SELECT count(*) FROM original_cvs",
    ):
        assert portal.call(_scalar, engine, count) == 0, count


def test_an_unknown_kind_is_rejected_by_the_database(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE, skill("a"))

    async def run() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE facts SET kind = 'hobby'"))

    with pytest.raises(IntegrityError):
        portal.call(run)


def test_the_v1_columns_all_exist_for_the_etl(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    async def columns() -> set[str]:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'facts'"
                )
            )
            return {row[0] for row in rows}

    assert portal.call(columns) >= V1_FACT_COLUMNS


def test_a_fact_keeps_its_source_and_confirmation_from_creation(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> Fact:
        async with uow() as tx:
            await tx.facts.add(
                ALICE,
                FactId(UUID(int=0xD001)),
                NewFact(FactKind.SKILL, "Go", FactSource.MANUAL, confirmed=True),
                NOW,
            )
            await tx.commit()
        return (await _all(uow, ALICE))[0]

    stored = portal.call(run)
    assert (stored.source, stored.confirmed, stored.job_id) == (
        FactSource.MANUAL,
        True,
        None,
    )


def test_a_fact_without_a_source_is_stored_as_cv(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, skill("Python"))
    (stored,) = portal.call(_all, uow, ALICE)
    assert (stored.source, stored.job_id) == (FactSource.CV, None)


def test_a_fact_shows_the_number_of_its_job_and_survives_the_job_deletion(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE, skill("Python"))
    job = UUID(int=0xE001)

    async def link() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO jobs (id, user_id, job_number, text, text_hash, "
                    "created_at) VALUES (:id, :user, 7, 'x', 'h', now())"
                ),
                {"id": job, "user": ALICE.value},
            )
            await conn.execute(text("UPDATE facts SET job_id = :job"), {"job": job})

    async def drop_job() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": job})

    portal.call(link)
    assert [f.job_id for f in portal.call(_all, uow, ALICE)] == [7]
    portal.call(drop_job)
    (kept,) = portal.call(_all, uow, ALICE)
    assert (kept.text, kept.job_id) == ("Python", None)


def test_parallel_batches_of_one_user_get_distinct_numbers_and_no_duplicates(
    portal: BlockingPortal, engine: AsyncEngine, uow: UnitOfWorkFactory
) -> None:
    use_cases = FactUseCases(unit_of_work_factory(engine), SystemClock(), RandomIds())
    actor = Actor(
        user_id=ALICE,
        channel=Channel.WEB,
        client_id="web",
        grant_id=None,
        scopes=frozenset(Scope),
        correlation_id="test",
    )

    async def run() -> list[int]:
        batches = [
            [
                FactInput(kind="skill", text=f"Skill {n}")
                for n in range(start, start + 6)
            ]
            for start in (0, 3, 6)
        ]
        await asyncio.gather(*(use_cases.save_facts(actor, batch) for batch in batches))
        return [f.number for f in await _all(uow, ALICE)]

    assert portal.call(run) == list(range(1, 13))
