"""Вакансії й подачі разом: «поданих не ховають», статус у списку й фільтри, подача в деталях."""

from datetime import timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.jobs import JobSearchInput
from domain.applications.application import ApplicationStatus
from domain.applications.errors import JobHasApplication
from domain.shared.errors import Conflict, InvalidFields, InvalidValue
from tests.support.applications import ApplicationWorld
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds

S = ApplicationStatus


@pytest.fixture
def world(
    portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
) -> ApplicationWorld:
    return ApplicationWorld(portal, clock, ids)


def jobs_at(world: ApplicationWorld, statuses: list[str | None]) -> list[int]:
    """Вакансії по одній на статус (None — без подачі); старіші мають менші номери."""
    numbers = []
    for position, status in enumerate(statuses):
        number = world.add_job(world.alice, f"Job {position}")
        world.clock.advance(timedelta(minutes=1))
        numbers.append(number)
        if status is not None:
            world.mark(world.alice, number)
            if status != "applied":
                world.move(world.alice, number, status)
    return numbers


# --- «поданих вакансій не ховають» ---


def test_an_applied_job_cannot_be_hidden(world: ApplicationWorld) -> None:
    job = world.add_job(world.alice)
    world.mark(world.alice, job)
    with pytest.raises(JobHasApplication) as caught:
        world.dismiss(world.alice, [job])
    assert caught.value.message == (
        "На вакансію 1 уже є подача — поданих вакансій не ховають."
    )
    assert world.job(world.alice, job).dismissed_at is None


def test_the_refusal_is_a_conflict_with_its_own_code(world: ApplicationWorld) -> None:
    job = world.add_job(world.alice)
    world.mark(world.alice, job)
    with pytest.raises(Conflict) as caught:
        world.dismiss(world.alice, [job])
    assert caught.value.code == "job_has_application"


def test_a_closed_application_also_keeps_the_job_visible(
    world: ApplicationWorld,
) -> None:
    job = world.add_job(world.alice)
    world.mark(world.alice, job)
    world.move(world.alice, job, "rejected")
    with pytest.raises(JobHasApplication):
        world.dismiss(world.alice, [job])


def test_a_batch_names_the_applied_item_and_hides_nothing(
    world: ApplicationWorld,
) -> None:
    first, second, third = (world.add_job(world.alice, f"Job {n}") for n in "abc")
    world.mark(world.alice, second)
    with pytest.raises(JobHasApplication) as caught:
        world.dismiss(world.alice, [first, second, third])
    assert caught.value.message == (
        "Елемент 2: на вакансію 2 уже є подача — поданих вакансій не ховають."
    )
    assert all(
        world.job(world.alice, n).dismissed_at is None for n in (first, second, third)
    )


def test_jobs_without_application_are_still_hidden(world: ApplicationWorld) -> None:
    first, second = (world.add_job(world.alice, f"Job {n}") for n in "ab")
    world.mark(world.alice, second)
    world.dismiss(world.alice, [first])
    assert world.listed(world.alice) == [second]


def test_an_application_of_another_user_does_not_block_hiding(
    world: ApplicationWorld,
) -> None:
    alice_job = world.add_job(world.alice, "Alice job")
    bob_job = world.add_job(world.bob, "Bob job")
    world.mark(world.bob, bob_job)
    world.dismiss(world.alice, [alice_job])
    assert world.listed(world.alice) == []


# --- подача в деталях ---


def test_a_job_without_application_has_none_in_its_details(
    world: ApplicationWorld,
) -> None:
    job = world.add_job(world.alice)
    assert world.job(world.alice, job).application is None


def test_the_details_carry_the_application(world: ApplicationWorld) -> None:
    job = world.add_job(world.alice)
    marked = world.mark(world.alice, job, channel="referral")
    world.clock.advance(timedelta(days=1))
    moved = world.move(world.alice, job, "replied")
    assert marked.status is S.APPLIED
    assert world.job(world.alice, job).application == moved


def test_the_application_of_another_user_is_not_in_the_details(
    world: ApplicationWorld,
) -> None:
    alice_job = world.add_job(world.alice, "Alice job")
    bob_job = world.add_job(world.bob, "Bob job")
    world.mark(world.alice, alice_job)
    assert world.job(world.bob, bob_job).application is None


# --- статус у списку й фільтри ---


def test_the_list_row_has_the_status_of_the_application(
    world: ApplicationWorld,
) -> None:
    jobs_at(world, [None, "applied", "interview"])
    found = world.portal.call(world.jobs.list_jobs, world.alice, JobSearchInput())
    assert {item.job_number: item.status for item in found} == {
        1: None,
        2: S.APPLIED,
        3: S.INTERVIEW,
    }


STATUSES = ["applied", "replied", "interview", "offer", "rejected", "withdrawn"]


@pytest.mark.parametrize("status", STATUSES)
def test_the_list_can_be_filtered_by_one_status(
    world: ApplicationWorld, status: str
) -> None:
    numbers = jobs_at(world, [None, *STATUSES])
    expected = numbers[1 + STATUSES.index(status)]
    assert world.listed(world.alice, status=status) == [expected]


def test_the_active_group_has_the_four_open_statuses(world: ApplicationWorld) -> None:
    numbers = jobs_at(world, [None, *STATUSES])
    # Новіші першими: застосунок без аналізу й тріажу сортується за часом.
    assert world.listed(world.alice, status="active") == [
        numbers[4],
        numbers[3],
        numbers[2],
        numbers[1],
    ]


def test_the_closed_group_has_rejected_and_withdrawn(world: ApplicationWorld) -> None:
    numbers = jobs_at(world, [None, *STATUSES])
    assert world.listed(world.alice, status="closed") == [numbers[6], numbers[5]]


def test_without_a_status_filter_every_job_is_listed(world: ApplicationWorld) -> None:
    numbers = jobs_at(world, [None, "applied", "rejected"])
    assert world.listed(world.alice) == [numbers[2], numbers[1], numbers[0]]


def test_the_order_of_the_list_does_not_depend_on_the_status(
    world: ApplicationWorld,
) -> None:
    numbers = jobs_at(world, ["offer", None, "rejected", "applied", None])
    assert world.listed(world.alice) == list(reversed(numbers))


def test_a_status_filter_with_a_bad_value_is_refused(world: ApplicationWorld) -> None:
    jobs_at(world, ["applied"])
    with pytest.raises(InvalidValue) as caught:
        world.listed(world.alice, status="hired")
    assert caught.value.field == "status"


def test_a_status_filter_works_together_with_the_others(
    world: ApplicationWorld,
) -> None:
    first = world.add_job(world.alice, "Python backend")
    second = world.add_job(world.alice, "Java backend")
    world.mark(world.alice, first)
    world.mark(world.alice, second)
    assert world.listed(world.alice, status="active", query="python") == [first]


def test_statuses_of_other_users_do_not_leak_into_the_filter(
    world: ApplicationWorld,
) -> None:
    alice_job = world.add_job(world.alice, "Alice job")
    bob_job = world.add_job(world.bob, "Bob job")
    world.mark(world.bob, bob_job)
    assert alice_job == bob_job == 1
    assert world.listed(world.alice, status="active") == []
    assert world.listed(world.bob, status="active") == [1]


def test_a_bad_status_and_a_bad_limit_are_reported_together(
    world: ApplicationWorld,
) -> None:
    with pytest.raises(InvalidFields) as caught:
        world.listed(world.alice, status="hired", limit=0)
    assert [p.field for p in caught.value.problems] == ["status", "limit"]
