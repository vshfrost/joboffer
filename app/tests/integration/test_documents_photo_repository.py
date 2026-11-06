"""Фото в документах на справжній базі: зв'язок CV з фото, «востаннє в CV», видалене фото."""

from datetime import datetime, timedelta
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.documents.document import Document
from domain.documents.ids import DocumentId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.photos.ids import PhotoId
from domain.photos.photo import NewPhoto
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_documents_repository import CV, LETTER, _job, uow
from tests.integration.test_jobs_repository import ALICE, NOW

__all__ = ["uow"]

_ids = iter(range(1, 10_000))


def _id() -> UUID:
    return UUID(int=0xF000 + next(_ids))


async def _photo(uow: UnitOfWorkFactory, user: UserId, label: str = "") -> PhotoId:
    photo_id = PhotoId(_id())
    async with uow() as tx:
        await tx.photos.add(
            user,
            photo_id,
            NewPhoto(data=b"jpeg", width=858, height=960, label=label),
            NOW,
        )
        await tx.commit()
    return photo_id


async def _save(
    uow: UnitOfWorkFactory,
    user: UserId,
    job: tuple[int, JobId],
    photo: PhotoId | None,
    when: datetime = NOW,
    letter: bool = False,
) -> Document:
    async with uow() as tx:
        saved = await tx.documents.add(
            user,
            DocumentId(_id()),
            job[1],
            LETTER if letter else CV,
            when,
            photo_id=photo,
        )
        await tx.commit()
        return saved


async def _listed(
    uow: UnitOfWorkFactory, user: UserId, job: tuple[int, JobId]
) -> list[Document]:
    async with uow() as tx:
        return await tx.documents.list_for_job(user, job[1])


async def _delete_photo(uow: UnitOfWorkFactory, user: UserId, number: int) -> None:
    async with uow() as tx:
        assert await tx.photos.delete(user, number)
        await tx.commit()


async def _last_used(
    uow: UnitOfWorkFactory, user: UserId
) -> dict[int, datetime | None]:
    async with uow() as tx:
        return {p.number: p.last_used_at for p in await tx.photos.all(user)}


def test_a_cv_saved_with_a_photo_reads_back_with_its_number(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    photo = portal.call(_photo, uow, ALICE)

    saved = portal.call(_save, uow, ALICE, job, photo)

    assert saved.photo_number == 1
    [stored] = portal.call(_listed, uow, ALICE, job)
    assert stored.photo_number == 1

    async def get() -> Document | None:
        async with uow() as tx:
            return await tx.documents.get(ALICE, saved.number)

    found = portal.call(get)
    assert found is not None
    assert found.photo_number == 1


def test_a_cv_saved_without_a_photo_has_none(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_photo, uow, ALICE)

    saved = portal.call(_save, uow, ALICE, job, None)

    assert saved.photo_number is None


def test_a_letter_is_saved_without_a_photo(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)

    assert portal.call(_save, uow, ALICE, job, None, NOW, True).photo_number is None


def test_last_used_follows_the_newest_cv_with_the_photo(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    first = portal.call(_photo, uow, ALICE)
    portal.call(_photo, uow, ALICE)
    assert portal.call(_last_used, uow, ALICE) == {1: None, 2: None}

    portal.call(_save, uow, ALICE, job, first, NOW + timedelta(days=1))
    portal.call(_save, uow, ALICE, job, first, NOW + timedelta(days=2))

    assert portal.call(_last_used, uow, ALICE) == {1: NOW + timedelta(days=2), 2: None}


def test_a_deleted_photo_leaves_the_cv_with_no_photo_and_all_the_rest(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    photo = portal.call(_photo, uow, ALICE)
    saved = portal.call(_save, uow, ALICE, job, photo)

    portal.call(_delete_photo, uow, ALICE, 1)

    [stored] = portal.call(_listed, uow, ALICE, job)
    assert stored.photo_number is None
    assert (stored.number, stored.version, stored.content) == (
        saved.number,
        saved.version,
        saved.content,
    )


def test_a_cv_cannot_point_to_a_photo_that_does_not_exist(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)

    with pytest.raises(IntegrityError):
        portal.call(_save, uow, ALICE, job, PhotoId(_id()))


def test_the_documents_table_has_the_photo_id_column_for_the_etl(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    async def columns() -> set[str]:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'documents'"
                )
            )
            return {row[0] for row in rows}

    assert "photo_id" in portal.call(columns)
