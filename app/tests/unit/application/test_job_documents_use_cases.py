"""Версії документів вакансії для вебу: без вмісту, з назвою файлу, наявністю PDF і звітом; лише власнику."""

import pytest

from application.contracts.actor import Actor
from application.contracts.documents import (
    CoverLetterData,
    JobDocumentData,
    KeywordCoverageData,
    LintData,
)
from application.contracts.profile import ContactsData
from domain.documents.document import DocumentKind
from domain.shared.errors import NotFound
from tests.unit.application.test_document_use_cases import (
    World,
    cv_data,
    letter_text,
    world,
)

__all__ = ["world"]


def seeded(world: World, actor: Actor | None = None) -> tuple[Actor, int, int]:
    owner = actor or world.alice
    return owner, world.seed(owner), world.fact(owner, "Python")


def listed(world: World, actor: Actor, number: int) -> tuple[JobDocumentData, ...]:
    return world.portal.call(world.documents.list_job_documents, actor, number)


def test_a_job_without_documents_has_an_empty_list(world: World) -> None:
    owner, number, _ = seeded(world)
    assert listed(world, owner, number) == ()


def test_a_missing_job_is_not_found(world: World) -> None:
    with pytest.raises(NotFound) as error:
        listed(world, world.alice, 9)
    assert error.value.message == "Вакансію 9 не знайдено."


def test_a_job_of_another_user_is_not_found(world: World) -> None:
    theirs = world.seed(world.bob)
    with pytest.raises(NotFound):
        listed(world, world.alice, theirs)


def test_documents_come_newest_first_with_kind_number_time_and_file_name(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.save_cv(owner, number, cv_data(fact, summary="First"))
    letter = world.save_letter(
        owner, number, CoverLetterData(text=letter_text(), fact_ids=(fact,))
    )
    cv = world.save_cv(owner, number, cv_data(fact, summary="Second"))

    items = listed(world, owner, number)

    assert [
        (i.document_number, i.job_number, i.kind, i.version, i.created_at, i.file_name)
        for i in items
    ] == [
        (3, number, DocumentKind.CV, 2, cv.created_at, "Alice_Example_CV.pdf"),
        (
            2,
            number,
            DocumentKind.COVER_LETTER,
            1,
            letter.created_at,
            "Alice_Example_Cover_Letter.pdf",
        ),
    ]


def test_the_report_of_the_current_cv_replaces_the_old_one(world: World) -> None:
    owner, number, fact = seeded(world)
    world.save_cv(owner, number, cv_data(fact, summary="Old"))
    world.analyse(owner, number, keywords=["Python", "Kafka"])
    world.save_cv(owner, number, cv_data(fact, summary="New"))

    [new] = listed(world, owner, number)

    assert new.lint == LintData(
        passed=True,
        pages=1,
        issues=(),
        keywords=KeywordCoverageData(
            covered=(), missing=("Python", "Kafka"), percent=0
        ),
    )


def test_the_file_name_follows_the_name_in_the_profile_today(world: World) -> None:
    owner, number, fact = seeded(world)
    world.save_cv(owner, number, cv_data(fact))
    world.set_profile(owner, ContactsData(full_name="Alex Example"))

    assert listed(world, owner, number)[0].file_name == "Alex_Example_CV.pdf"


def test_a_missing_file_is_reported_per_document_not_hidden(world: World) -> None:
    owner, number, fact = seeded(world)
    world.save_cv(owner, number, cv_data(fact, summary="First"))
    world.save_letter(
        owner, number, CoverLetterData(text=letter_text(), fact_ids=(fact,))
    )
    world.pdf.files.pop(next(iter(world.pdf.files)))

    letter, cv = listed(world, owner, number)

    assert (cv.pdf_available, letter.pdf_available) == (False, True)


def test_a_user_never_sees_documents_of_another(world: World) -> None:
    mine, mine_job, mine_fact = seeded(world, world.alice)
    theirs, their_job, their_fact = seeded(world, world.bob)
    world.save_cv(mine, mine_job, cv_data(mine_fact))
    world.save_cv(theirs, their_job, cv_data(their_fact, summary="Theirs"))

    assert mine_job == their_job
    [only] = listed(world, theirs, their_job)
    assert only.file_name == "Bob_Example_CV.pdf"
    assert len(listed(world, mine, mine_job)) == 1
