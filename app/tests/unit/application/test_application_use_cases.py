"""Use cases подач: позначити поданою, рухати воронкою, дата за Мадридом, ізоляція користувачів."""

from datetime import date, timedelta

import pytest
from anyio.from_thread import BlockingPortal

from domain.applications.application import (
    ApplicationChannel,
    ApplicationStatus,
    AtsPlatform,
)
from domain.shared.errors import InvalidFields, InvalidValue, NotFound
from tests.support.applications import MADRID_AFTER_MIDNIGHT, ApplicationWorld
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds

S = ApplicationStatus
FORWARD_FROM_APPLIED = (S.REPLIED, S.INTERVIEW, S.OFFER, S.REJECTED, S.WITHDRAWN)


@pytest.fixture
def world(
    portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
) -> ApplicationWorld:
    return ApplicationWorld(portal, clock, ids)


def test_marking_a_job_applied_creates_an_applied_application(
    world: ApplicationWorld,
) -> None:
    job = world.add_job(world.alice)
    saved = world.mark(
        world.alice,
        job,
        channel="ats",
        applied_on="2026-01-01",
        ats="lever",
        company_domains=["https://www.Acme.com"],
        company_emails=["HR@acme.com"],
    )
    assert (saved.job_number, saved.status) == (job, S.APPLIED)
    assert (saved.applied_on, saved.channel, saved.ats) == (
        date(2026, 1, 1),
        ApplicationChannel.ATS,
        AtsPlatform.LEVER,
    )
    assert (saved.company_domains, saved.company_emails) == (
        ("acme.com",),
        ("hr@acme.com",),
    )
    assert saved.status_changed_at == world.clock.now()
    assert world.application(world.alice, job) == saved


def test_a_new_application_offers_every_forward_move(world: ApplicationWorld) -> None:
    job = world.add_job(world.alice)
    assert world.mark(world.alice, job).allowed_transitions == FORWARD_FROM_APPLIED


def test_the_default_date_is_today_in_madrid(
    portal: BlockingPortal, ids: SequentialIds
) -> None:
    world = ApplicationWorld(portal, FakeClock(MADRID_AFTER_MIDNIGHT), ids)
    job = world.add_job(world.alice)
    assert world.mark(world.alice, job).applied_on == date(2026, 3, 2)


def test_a_date_after_madrid_today_is_in_the_future(
    portal: BlockingPortal, ids: SequentialIds
) -> None:
    world = ApplicationWorld(portal, FakeClock(MADRID_AFTER_MIDNIGHT), ids)
    job = world.add_job(world.alice)
    assert world.mark(world.alice, job, applied_on="2026-03-02").applied_on == date(
        2026, 3, 2
    )
    with pytest.raises(InvalidFields) as caught:
        world.mark(world.alice, job, applied_on="2026-03-03")
    assert caught.value.message == "Дата подачі не може бути в майбутньому."


def test_a_bad_date_is_refused_and_nothing_is_saved(world: ApplicationWorld) -> None:
    job = world.add_job(world.alice)
    with pytest.raises(InvalidFields) as caught:
        world.mark(world.alice, job, applied_on="02.03.2026")
    assert (caught.value.field, caught.value.message) == (
        "applied_on",
        "Дата подачі — у форматі YYYY-MM-DD.",
    )
    assert world.application(world.alice, job) is None


def test_every_problem_of_the_form_is_reported_together(
    world: ApplicationWorld,
) -> None:
    job = world.add_job(world.alice)
    with pytest.raises(InvalidFields) as caught:
        world.mark(world.alice, job, channel="phone", company_domains=["no"])
    assert [p.field for p in caught.value.problems] == ["channel", "company_domains"]


def test_an_unknown_job_cannot_be_marked_applied(world: ApplicationWorld) -> None:
    with pytest.raises(NotFound) as caught:
        world.mark(world.alice, 99)
    assert caught.value.message == "Вакансію 99 не знайдено."


def test_marking_again_replaces_the_details_and_keeps_the_status(
    world: ApplicationWorld,
) -> None:
    job = world.add_job(world.alice)
    world.mark(world.alice, job, channel="email", company_emails=["a@acme.com"])
    world.clock.advance(timedelta(days=2))
    world.move(world.alice, job, "interview")
    changed_at = world.clock.now()
    world.clock.advance(timedelta(days=1))
    again = world.mark(
        world.alice,
        job,
        channel="linkedin",
        applied_on="2026-01-01",
        ats="ashby",
        company_domains=["acme.com"],
    )
    assert again.status is S.INTERVIEW
    assert again.status_changed_at == changed_at
    assert (again.channel, again.ats, again.company_domains, again.company_emails) == (
        ApplicationChannel.LINKEDIN,
        AtsPlatform.ASHBY,
        ("acme.com",),
        (),
    )


def test_marking_a_hidden_job_applied_brings_it_back_to_the_list(
    world: ApplicationWorld,
) -> None:
    job = world.add_job(world.alice)
    world.dismiss(world.alice, [job])
    assert world.listed(world.alice) == []
    world.mark(world.alice, job)
    assert world.listed(world.alice) == [job]
    assert world.job(world.alice, job).dismissed_at is None


def test_refused_details_leave_a_hidden_job_hidden(world: ApplicationWorld) -> None:
    job = world.add_job(world.alice)
    world.dismiss(world.alice, [job])
    with pytest.raises(InvalidFields):
        world.mark(world.alice, job, channel="phone")
    assert world.job(world.alice, job).dismissed_at is not None


@pytest.mark.parametrize("new", FORWARD_FROM_APPLIED)
def test_a_forward_move_sets_the_status_and_its_time(
    world: ApplicationWorld, new: ApplicationStatus
) -> None:
    job = world.add_job(world.alice)
    world.mark(world.alice, job, channel="ats", ats="lever")
    world.clock.advance(timedelta(days=3))
    moved = world.move(world.alice, job, new.value)
    assert moved.status is new
    assert moved.status_changed_at == world.clock.now()
    assert (moved.channel, moved.ats) == (ApplicationChannel.ATS, AtsPlatform.LEVER)
    assert world.application(world.alice, job) == moved


def test_the_moved_application_lists_only_the_moves_still_allowed(
    world: ApplicationWorld,
) -> None:
    job = world.add_job(world.alice)
    world.mark(world.alice, job)
    assert world.move(world.alice, job, "interview").allowed_transitions == (
        S.OFFER,
        S.REJECTED,
        S.WITHDRAWN,
    )
    assert world.move(world.alice, job, "rejected").allowed_transitions == ()


def test_the_same_status_changes_nothing_and_keeps_its_time(
    world: ApplicationWorld,
) -> None:
    job = world.add_job(world.alice)
    before = world.mark(world.alice, job)
    world.clock.advance(timedelta(days=5))
    after = world.move(world.alice, job, "applied")
    assert after == before
    assert after.status_changed_at == before.status_changed_at


def test_a_closed_application_cannot_be_moved(world: ApplicationWorld) -> None:
    job = world.add_job(world.alice)
    world.mark(world.alice, job)
    closed = world.move(world.alice, job, "rejected")
    with pytest.raises(InvalidValue) as caught:
        world.move(world.alice, job, "offer")
    assert caught.value.message == (
        "Подачу вже закрито (rejected): статус більше не змінюється."
    )
    assert world.application(world.alice, job) == closed


def test_a_move_back_is_refused_and_the_status_stays(world: ApplicationWorld) -> None:
    job = world.add_job(world.alice)
    world.mark(world.alice, job)
    world.move(world.alice, job, "interview")
    with pytest.raises(InvalidValue) as caught:
        world.move(world.alice, job, "replied")
    assert caught.value.message.startswith("Статус interview → replied неможливий")
    status = world.application(world.alice, job)
    assert status is not None
    assert status.status is S.INTERVIEW


def test_an_unknown_status_is_refused(world: ApplicationWorld) -> None:
    job = world.add_job(world.alice)
    world.mark(world.alice, job)
    with pytest.raises(InvalidValue) as caught:
        world.move(world.alice, job, "hired")
    assert caught.value.field == "status"


def test_moving_a_job_without_application_says_to_mark_it_first(
    world: ApplicationWorld,
) -> None:
    job = world.add_job(world.alice)
    with pytest.raises(NotFound) as caught:
        world.move(world.alice, job, "replied")
    assert caught.value.message == (
        f"Подачі на вакансію {job} нема: спершу mark_applied."
    )


def test_a_job_without_application_has_none(world: ApplicationWorld) -> None:
    job = world.add_job(world.alice)
    assert world.application(world.alice, job) is None
    assert world.application(world.alice, 99) is None


def test_a_user_does_not_see_the_application_of_another(
    world: ApplicationWorld,
) -> None:
    job = world.add_job(world.alice)
    world.mark(world.alice, job)
    assert world.application(world.bob, job) is None
    with pytest.raises(NotFound):
        world.move(world.bob, job, "replied")


def test_a_user_cannot_mark_a_job_of_another(world: ApplicationWorld) -> None:
    job = world.add_job(world.alice)
    with pytest.raises(NotFound):
        world.mark(world.bob, job)
    assert world.application(world.alice, job) is None


def test_applications_of_two_users_on_the_same_number_are_independent(
    world: ApplicationWorld,
) -> None:
    alice_job = world.add_job(world.alice, "Alice job")
    bob_job = world.add_job(world.bob, "Bob job")
    assert alice_job == bob_job == 1
    world.mark(world.alice, alice_job, channel="email")
    world.mark(world.bob, bob_job, channel="referral")
    world.move(world.bob, bob_job, "offer")
    alice = world.application(world.alice, alice_job)
    bob = world.application(world.bob, bob_job)
    assert alice is not None
    assert bob is not None
    assert (alice.channel, alice.status) == (ApplicationChannel.EMAIL, S.APPLIED)
    assert (bob.channel, bob.status) == (ApplicationChannel.REFERRAL, S.OFFER)
