"""PostgresPhotos на справжній базі: номери на користувача, байти без втрат, `last_used_at` з документів,
видалення не чіпає документи, каскад, схема для ETL."""

import json
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.documents.ids import DocumentId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.photos.ids import PhotoId
from domain.photos.photo import NewPhoto, Photo
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, posting, uow

__all__ = ["uow"]

_ids = iter(range(1, 10_000))

# Усі поля таблиці `photos` v1 (крім ключів): ETL у B12 переносить їх без втрат.
V1_PHOTO_COLUMNS = {"label", "data", "width", "height", "created_at"}
EVERY_BYTE = bytes(range(256)) * 4


def _id() -> UUID:
    return UUID(int=0xE000 + next(_ids))


def new_photo(data: bytes = b"jpeg", label: str = "") -> NewPhoto:
    return NewPhoto(data=data, width=858, height=960, label=label)


async def _add(
    uow: UnitOfWorkFactory,
    user: UserId,
    photo: NewPhoto | None = None,
    now: datetime = NOW,
    number: int | None = None,
) -> Photo:
    async with uow() as tx:
        added = await tx.photos.add(
            user, PhotoId(_id()), photo or new_photo(), now, number
        )
        await tx.commit()
        return added


async def _all(uow: UnitOfWorkFactory, user: UserId) -> list[Photo]:
    async with uow() as tx:
        return await tx.photos.all(user)


async def _data(uow: UnitOfWorkFactory, user: UserId, number: int) -> bytes | None:
    async with uow() as tx:
        return await tx.photos.data(user, number)


async def _delete(uow: UnitOfWorkFactory, user: UserId, number: int) -> bool:
    async with uow() as tx:
        deleted = await tx.photos.delete(user, number)
        await tx.commit()
        return deleted


async def _cv_with_photo(
    uow: UnitOfWorkFactory,
    engine: AsyncEngine,
    user: UserId,
    photo_number: int | None,
    created_at: datetime,
    document_number: int,
) -> None:
    """Версія CV (сира вставка) з фото в шапці: так `last_used_at` з'являється в документах."""
    job_id = JobId(_id())
    async with uow() as tx:
        await tx.jobs.add(user, job_id, posting(f"job {document_number}"), NOW)
        await tx.commit()
    async with engine.begin() as conn:
        photo_id = None
        if photo_number is not None:
            photo_id = (
                await conn.execute(
                    text(
                        "SELECT id FROM photos "
                        "WHERE user_id = :user AND photo_number = :number"
                    ),
                    {"user": user.value, "number": photo_number},
                )
            ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO documents (id, user_id, document_number, job_id, kind, "
                "version, content, created_at, photo_id) VALUES (:id, :user, :number, "
                ":job, 'cv', 1, CAST(:content AS jsonb), :created, :photo)"
            ),
            {
                "id": DocumentId(_id()).value,
                "user": user.value,
                "number": document_number,
                "job": job_id.value,
                "content": json.dumps({}),
                "created": created_at,
                "photo": photo_id,
            },
        )


async def _scalar(engine: AsyncEngine, sql: str) -> object:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar()


def test_numbers_start_at_one_and_grow_per_user(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first = portal.call(_add, uow, ALICE)
    second = portal.call(_add, uow, ALICE)
    bobs = portal.call(_add, uow, BOB)
    assert (first.number, second.number, bobs.number) == (1, 2, 1)


def test_an_added_photo_keeps_its_fields_and_was_never_used(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    added = portal.call(_add, uow, ALICE, new_photo(label="Office"))
    (stored,) = portal.call(_all, uow, ALICE)
    assert stored == added
    assert (stored.label, stored.width, stored.height) == ("Office", 858, 960)
    assert (stored.created_at, stored.last_used_at) == (NOW, None)


def test_an_explicit_number_is_kept_and_the_counter_continues_after_it(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    assert portal.call(_add, uow, ALICE, None, NOW, 41).number == 41
    assert portal.call(_add, uow, ALICE).number == 42


def test_a_smaller_explicit_number_does_not_lower_the_counter(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, None, NOW, 10)
    portal.call(_add, uow, ALICE, None, NOW, 3)
    assert portal.call(_add, uow, ALICE).number == 11


def test_a_deleted_number_is_not_reused(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE)
    portal.call(_add, uow, ALICE)
    portal.call(_delete, uow, ALICE, 2)
    assert portal.call(_add, uow, ALICE).number == 3


def test_a_rolled_back_addition_does_not_spend_a_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def abandoned() -> None:
        async with uow() as tx:
            await tx.photos.add(ALICE, PhotoId(_id()), new_photo(), NOW)

    portal.call(abandoned)
    assert portal.call(_all, uow, ALICE) == []
    assert portal.call(_add, uow, ALICE).number == 1


def test_the_bytes_come_back_exactly(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, new_photo(EVERY_BYTE))
    assert portal.call(_data, uow, ALICE, 1) == EVERY_BYTE


def test_a_list_is_newest_first(portal: BlockingPortal, uow: UnitOfWorkFactory) -> None:
    portal.call(_add, uow, ALICE, None, NOW)
    portal.call(_add, uow, ALICE, None, NOW + timedelta(days=2))
    portal.call(_add, uow, ALICE, None, NOW + timedelta(days=1))
    assert [p.number for p in portal.call(_all, uow, ALICE)] == [2, 3, 1]


def test_equal_times_are_listed_by_the_higher_number_first(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE)
    portal.call(_add, uow, ALICE)
    assert [p.number for p in portal.call(_all, uow, ALICE)] == [2, 1]


def test_another_users_photos_are_invisible(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, new_photo(b"alice"))
    assert portal.call(_all, uow, BOB) == []
    assert portal.call(_data, uow, BOB, 1) is None
    assert portal.call(_data, uow, ALICE, 1) == b"alice"


def test_last_used_is_the_time_of_the_newest_cv_with_the_photo(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE)
    portal.call(_add, uow, ALICE)
    later = NOW + timedelta(days=3)
    portal.call(_cv_with_photo, uow, engine, ALICE, 1, NOW + timedelta(days=1), 1)
    portal.call(_cv_with_photo, uow, engine, ALICE, 1, later, 2)
    portal.call(_cv_with_photo, uow, engine, ALICE, None, NOW + timedelta(days=9), 3)

    by_number = {p.number: p.last_used_at for p in portal.call(_all, uow, ALICE)}

    assert by_number == {1: later, 2: None}


def test_deleting_a_photo_returns_true_and_removes_it(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE)
    assert portal.call(_delete, uow, ALICE, 1) is True
    assert portal.call(_all, uow, ALICE) == []
    assert portal.call(_data, uow, ALICE, 1) is None
    assert portal.call(_delete, uow, ALICE, 1) is False


def test_deleting_someone_elses_photo_does_nothing(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, ALICE, new_photo(b"alice"))
    assert portal.call(_delete, uow, BOB, 1) is False
    assert portal.call(_data, uow, ALICE, 1) == b"alice"


def test_deleting_a_used_photo_keeps_the_document_and_clears_its_photo(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE)
    portal.call(_cv_with_photo, uow, engine, ALICE, 1, NOW, 1)

    portal.call(_delete, uow, ALICE, 1)

    assert portal.call(_scalar, engine, "SELECT count(*) FROM documents") == 1
    assert (
        portal.call(_scalar, engine, "SELECT photo_id IS NULL FROM documents") is True
    )


@pytest.mark.parametrize("number", [0, -1, 2**31, 2**63])
def test_a_number_outside_the_database_range_is_just_missing(
    portal: BlockingPortal, uow: UnitOfWorkFactory, number: int
) -> None:
    portal.call(_add, uow, ALICE)
    assert portal.call(_data, uow, ALICE, number) is None
    assert portal.call(_delete, uow, ALICE, number) is False


def test_the_schema_rejects_a_repeated_number_of_one_user(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE, None, NOW, 5)
    with pytest.raises(IntegrityError):
        portal.call(_add, uow, ALICE, None, NOW, 5)


def test_removing_a_user_removes_their_photos_and_counter(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, ALICE)

    async def remove() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM users WHERE id = :id"), {"id": ALICE.value}
            )

    portal.call(remove)

    assert portal.call(_scalar, engine, "SELECT count(*) FROM photos") == 0
    assert portal.call(_scalar, engine, "SELECT count(*) FROM photo_counters") == 0


def test_the_photos_table_keeps_every_v1_column_for_the_etl(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    async def columns() -> set[str]:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'photos'"
                )
            )
            return {row[0] for row in rows}

    assert portal.call(columns) >= V1_PHOTO_COLUMNS


def test_documents_have_a_photo_id_column(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    sql = (
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name = 'documents' AND column_name = 'photo_id'"
    )
    assert portal.call(_scalar, engine, sql) == 1
