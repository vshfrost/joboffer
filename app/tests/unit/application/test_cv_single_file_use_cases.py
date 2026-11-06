"""Файл CV вакансії один, останній: нове збереження прибирає попереднє CV разом з його PDF.
Подача пам'ятає лише версію, не файл (див. `test_cv_version_use_cases`)."""

import pytest

from domain.documents.document import DocumentKind
from domain.shared.errors import NotFound
from tests.unit.application.test_document_pdf_use_cases import seeded
from tests.unit.application.test_document_use_cases import World, cv_data, world

__all__ = ["world"]


def test_a_new_save_cv_leaves_one_cv_of_the_job_the_latest(world: World) -> None:
    owner, number, fact = seeded(world)
    world.save_cv(owner, number, cv_data(fact, summary="First"))
    second = world.save_cv(owner, number, cv_data(fact, summary="Second"))

    kept = [d for d in world.listed(owner, number) if d.kind is DocumentKind.CV]

    assert [d.document_number for d in kept] == [second.document_number]


def test_a_new_save_cv_leaves_one_pdf_file_the_latest_and_the_old_one_is_gone(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    first = world.save_cv(owner, number, cv_data(fact, summary="First"))
    second = world.save_cv(owner, number, cv_data(fact, summary="Second"))

    assert len(world.pdf.files) == 1
    assert world.portal.call(world.documents.get_pdf, owner, second.document_number)
    with pytest.raises(NotFound):
        world.portal.call(world.documents.get_pdf, owner, first.document_number)
