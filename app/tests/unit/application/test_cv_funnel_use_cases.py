"""Звіт воронки за версіями CV: для кожної версії окремо подачі, відповіді й інтервʼю.

Відповідь — подача зайшла в replied, interview чи offer; інтервʼю — в interview чи offer.
Відмова й відкликання рахуються лише як подачі: історії статусів подача не тримає.
Подачі без CV і старі подачі — одна група «невідомо» (`cv_number` None)."""

from dataclasses import replace
from datetime import date

from application.contracts.actor import Actor
from application.contracts.applications import CvFunnelData, CvFunnelRowData
from domain.applications.application import CvVersion
from tests.support.applications import ApplicationWorld
from tests.unit.application.test_application_use_cases import world

__all__ = ["world"]

FIRST = CvVersion(number=1, saved_on=date(2026, 1, 5), coverage_percent=83)
SECOND = CvVersion(number=2, saved_on=date(2026, 1, 8), coverage_percent=50)


def applied(
    world: ApplicationWorld, actor: Actor, status: str, cv: CvVersion | None
) -> int:
    """Нова вакансія, подана з цією версією CV й доведена до статусу."""
    # Той самий текст — та сама вакансія (дубль): кожна подача отримує свою.
    job = world.add_job(actor, f"Backend engineer, opening {len(world.store.jobs)}")
    world.mark(actor, job)
    if status != "applied":
        world.move(actor, job, status)
    key = (actor.user_id, job)
    world.store.applications[key] = replace(world.store.applications[key], cv=cv)
    return job


def funnel(world: ApplicationWorld, actor: Actor) -> CvFunnelData:
    return world.portal.call(world.applications.cv_funnel, actor)


def row(
    cv: CvVersion | None, applications: int, replies: int, interviews: int
) -> CvFunnelRowData:
    return CvFunnelRowData(
        cv_number=None if cv is None else cv.number,
        saved_on=None if cv is None else cv.saved_on,
        coverage_percent=None if cv is None else cv.coverage_percent,
        applications=applications,
        replies=replies,
        interviews=interviews,
    )


def test_applications_replies_and_interviews_are_counted_separately_by_version(
    world: ApplicationWorld,
) -> None:
    for status in ("applied", "applied", "replied", "interview"):
        applied(world, world.alice, status, FIRST)
    for status in ("applied", "replied"):
        applied(world, world.alice, status, SECOND)

    assert funnel(world, world.alice).rows == (
        row(FIRST, applications=4, replies=2, interviews=1),
        row(SECOND, applications=2, replies=1, interviews=0),
    )


def test_a_reply_is_counted_for_every_status_that_follows_it(
    world: ApplicationWorld,
) -> None:
    for status in ("applied", "replied", "interview", "offer"):
        applied(world, world.alice, status, FIRST)

    assert funnel(world, world.alice).rows == (
        row(FIRST, applications=4, replies=3, interviews=2),
    )


def test_rejected_and_withdrawn_applications_count_only_as_applications(
    world: ApplicationWorld,
) -> None:
    applied(world, world.alice, "rejected", FIRST)
    applied(world, world.alice, "withdrawn", FIRST)

    assert funnel(world, world.alice).rows == (
        row(FIRST, applications=2, replies=0, interviews=0),
    )


def test_versions_are_listed_by_number_and_unknown_comes_last(
    world: ApplicationWorld,
) -> None:
    applied(world, world.alice, "applied", None)
    applied(world, world.alice, "applied", SECOND)
    applied(world, world.alice, "applied", FIRST)

    rows = funnel(world, world.alice).rows

    assert [item.cv_number for item in rows] == [1, 2, None]


def test_applications_without_a_cv_and_old_applications_are_one_unknown_group(
    world: ApplicationWorld,
) -> None:
    applied(world, world.alice, "applied", None)
    applied(world, world.alice, "interview", None)

    assert funnel(world, world.alice).rows == (
        row(None, applications=2, replies=1, interviews=1),
    )


def test_an_application_without_a_cv_marked_through_the_use_case_is_unknown(
    world: ApplicationWorld,
) -> None:
    job = world.add_job(world.alice)
    world.mark(world.alice, job)

    assert funnel(world, world.alice).rows == (
        row(None, applications=1, replies=0, interviews=0),
    )


def test_no_applications_give_an_empty_report(world: ApplicationWorld) -> None:
    assert funnel(world, world.alice).rows == ()


def test_the_report_counts_only_the_applications_of_the_user(
    world: ApplicationWorld,
) -> None:
    applied(world, world.alice, "interview", FIRST)
    applied(world, world.bob, "applied", FIRST)

    assert funnel(world, world.alice).rows == (
        row(FIRST, applications=1, replies=1, interviews=1),
    )
