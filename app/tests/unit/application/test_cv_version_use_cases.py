"""Подача пам'ятає версію CV, з якою подались: номер документа, день збереження і покриття слів
вакансії. Файл CV лишається один, останній; нове збереження подачу не змінює. Подача без CV
і стара подача (до цієї можливості) мають версію «невідомо»."""

from datetime import date, timedelta

from application.applications.use_cases import ApplicationUseCases
from application.contracts.actor import Actor
from application.contracts.applications import (
    ApplicationData,
    ApplicationInput,
    CvVersionData,
)
from domain.applications.application import (
    Application,
    ApplicationChannel,
    ApplicationStatus,
)
from tests.support.applications import InMemoryApplicationUnitOfWork
from tests.unit.application.test_document_pdf_use_cases import seeded
from tests.unit.application.test_document_use_cases import (
    World,
    cv_data,
    world,
)

__all__ = ["world"]

# Годинник тестів стоїть на 2026-01-01 09:00 UTC; перше CV зберігається того ж дня.
SAVED_ON = date(2026, 1, 1)


def applications_of(world: World) -> ApplicationUseCases:
    return ApplicationUseCases(
        lambda: InMemoryApplicationUnitOfWork(world.jobs_store, world.docs_store),
        world.clock,
    )


def mark(world: World, owner: Actor, number: int) -> ApplicationData:
    return world.portal.call(
        applications_of(world).mark_applied,
        owner,
        number,
        ApplicationInput(channel="ats"),
    )


def application(world: World, owner: Actor, number: int) -> ApplicationData | None:
    return world.portal.call(applications_of(world).get_application, owner, number)


def old_application(world: World, number: int) -> Application:
    """Подача у формі, що була до версій CV: без жодного поля про них."""
    return Application(
        job_number=number,
        status=ApplicationStatus.APPLIED,
        applied_on=SAVED_ON,
        channel=ApplicationChannel.ATS,
        ats=None,
        company_domains=(),
        company_emails=(),
        status_changed_at=world.clock.now(),
    )


def analysed_with_a_cv(world: World) -> tuple[Actor, int, int]:
    """Вакансія зі словами Payments і Kafka та CV, де є лише Payments (покриття 50 %)."""
    owner, number, fact = seeded(world)
    world.analyse(owner, number, keywords=["Payments", "Kafka"])
    world.save_cv(owner, number, cv_data(fact))
    return owner, number, fact


def test_marking_applied_records_the_number_date_and_coverage_of_the_current_cv(
    world: World,
) -> None:
    owner, number, _ = analysed_with_a_cv(world)
    world.clock.advance(timedelta(days=3))

    saved = mark(world, owner, number)

    assert saved.applied_on == date(2026, 1, 4)
    assert saved.cv == CvVersionData(number=1, saved_on=SAVED_ON, coverage_percent=50)
    assert application(world, owner, number) == saved


def test_the_cv_version_is_the_latest_cv_of_that_job_when_there_were_several_saves(
    world: World,
) -> None:
    owner, number, fact = analysed_with_a_cv(world)
    world.clock.advance(timedelta(days=1))
    world.save_cv(owner, number, cv_data(fact, summary="Payments and Kafka backend"))

    saved = mark(world, owner, number)

    assert saved.cv == CvVersionData(
        number=2, saved_on=date(2026, 1, 2), coverage_percent=100
    )


def test_a_cv_of_another_job_is_not_the_version_of_this_application(
    world: World,
) -> None:
    owner, _, _ = analysed_with_a_cv(world)
    other = world.seed(owner)

    assert mark(world, owner, other).cv is None


def test_a_cv_saved_before_any_analysis_has_a_version_without_coverage(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.save_cv(owner, number, cv_data(fact))

    saved = mark(world, owner, number)

    assert saved.cv == CvVersionData(number=1, saved_on=SAVED_ON, coverage_percent=None)


def test_the_application_does_not_change_after_a_new_save_cv(world: World) -> None:
    owner, number, fact = analysed_with_a_cv(world)
    before = mark(world, owner, number)
    world.clock.advance(timedelta(days=1))

    world.save_cv(owner, number, cv_data(fact, summary="Payments and Kafka backend"))

    assert application(world, owner, number) == before
    assert before.cv == CvVersionData(number=1, saved_on=SAVED_ON, coverage_percent=50)


def test_marking_again_after_a_new_cv_records_that_newer_version(
    world: World,
) -> None:
    owner, number, fact = analysed_with_a_cv(world)
    mark(world, owner, number)
    world.clock.advance(timedelta(days=1))
    world.save_cv(owner, number, cv_data(fact, summary="Payments and Kafka backend"))

    again = mark(world, owner, number)

    assert again.cv == CvVersionData(
        number=2, saved_on=date(2026, 1, 2), coverage_percent=100
    )


def test_an_application_without_a_cv_has_no_version_and_marking_still_works(
    world: World,
) -> None:
    owner, number, _ = seeded(world)

    saved = mark(world, owner, number)

    assert saved.cv is None
    assert saved.status.value == "applied"


def test_an_application_from_before_versions_were_remembered_reads_without_a_version(
    world: World,
) -> None:
    owner, number, _ = seeded(world)
    world.jobs_store.applications[(owner.user_id, number)] = old_application(
        world, number
    )

    read = application(world, owner, number)

    assert read is not None
    assert read.cv is None


# --- звіт бачить версію, з якою подались, а не найновіше CV -------------------


def test_the_report_keeps_the_application_under_the_cv_it_was_made_with(
    world: World,
) -> None:
    owner, number, fact = analysed_with_a_cv(world)
    mark(world, owner, number)
    world.clock.advance(timedelta(days=1))
    world.save_cv(owner, number, cv_data(fact, summary="Payments and Kafka backend"))
    world.portal.call(
        applications_of(world).set_application_status, owner, number, "interview"
    )

    report = world.portal.call(applications_of(world).cv_funnel, owner)

    assert [
        (r.cv_number, r.saved_on, r.coverage_percent, r.applications, r.interviews)
        for r in report.rows
    ] == [(1, SAVED_ON, 50, 1, 1)]
