"""Use cases вакансій: номери, дублі, LinkedIn-дописування, список, приховування, ізоляція."""

from datetime import timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.jobs import (
    AddedJob,
    AddOutcome,
    JobData,
    JobInput,
    JobSearchInput,
    JobSummaryData,
)
from application.jobs.use_cases import JobUseCases
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.shared.errors import InvalidFields, InvalidValue, NotFound
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store

POSTING = "Senior Python engineer. Remote. Asyncio, Postgres."
ALERT_LINK = (
    "https://es.linkedin.com/comm/jobs/view/dev-at-acme-4012345678/?trackingId=x"
)


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.store = Store.empty()
        self.alice = self._actor()
        self.bob = self._actor()
        self.use_cases = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.store), clock, ids
        )

    def _actor(self) -> Actor:
        return Actor(
            user_id=UserId(self.ids.new()),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )

    def add(self, actor: Actor, **fields: str) -> AddedJob:
        data = JobInput(**({"text": POSTING} | fields))
        return self.portal.call(self.use_cases.add_job, actor, data)

    def seed_alert(self, actor: Actor, *, title: str, company: str) -> int:
        """Вакансія з листа-алерту LinkedIn (її створить B10): без тексту."""

        async def seed() -> int:
            async with InMemoryJobUnitOfWork(self.store) as uow:
                number = await uow.jobs.add(
                    actor.user_id,
                    JobId(self.ids.new()),
                    NewJob(
                        text=None,
                        url="https://www.linkedin.com/jobs/view/4012345678",
                        title=title,
                        company=company,
                        linkedin_id="4012345678",
                        source="linkedin_alert",
                    ),
                    self.clock.now(),
                )
                await uow.commit()
                return number

        return self.portal.call(seed)

    def get(self, actor: Actor, number: int) -> JobData:
        return self.portal.call(self.use_cases.get_job, actor, number)

    def listed(self, actor: Actor, **fields: object) -> list[JobSummaryData]:
        data = JobSearchInput(**fields)  # type: ignore[arg-type]
        return self.portal.call(self.use_cases.list_jobs, actor, data)

    def numbers(self, actor: Actor, **fields: object) -> list[int]:
        return [item.job_number for item in self.listed(actor, **fields)]

    def dismiss(
        self, actor: Actor, numbers: list[int], reason: str = "не цікаво"
    ) -> None:
        self.portal.call(self.use_cases.dismiss_jobs, actor, numbers, reason)

    def restore(self, actor: Actor, number: int) -> None:
        self.portal.call(self.use_cases.restore_job, actor, number)


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def test_the_first_job_of_a_user_is_number_one_and_the_next_follows(
    world: World,
) -> None:
    first = world.add(world.alice, text="one")
    second = world.add(world.alice, text="two")
    assert first == AddedJob(1, AddOutcome.CREATED)
    assert second == AddedJob(2, AddOutcome.CREATED)
    assert not first.duplicate


def test_numbers_are_counted_per_user(world: World) -> None:
    world.add(world.alice, text="one")
    world.add(world.alice, text="two")
    assert world.add(world.bob, text="one").job_number == 1


def test_a_new_job_keeps_all_its_fields(world: World) -> None:
    added = world.add(
        world.alice,
        text=POSTING,
        url="https://Acme.com/jobs/1/?utm_source=x#top",
        title="Backend Engineer",
        company="Acme",
    )
    job = world.get(world.alice, added.job_number)
    assert job == JobData(
        job_number=1,
        source="manual",
        url="https://acme.com/jobs/1",
        title="Backend Engineer",
        company="Acme",
        location=None,
        text=POSTING,
        created_at=world.clock.now(),
        needs_text=False,
        dismissed_at=None,
        dismiss_reason=None,
    )


def test_the_same_text_in_another_case_and_spacing_is_the_existing_job(
    world: World,
) -> None:
    first = world.add(world.alice, text=POSTING)
    again = world.add(
        world.alice, text="  SENIOR python\nENGINEER. remote.  Asyncio, Postgres."
    )
    assert again == AddedJob(first.job_number, AddOutcome.DUPLICATE)
    assert again.duplicate
    assert len(world.listed(world.alice)) == 1


def test_the_same_url_with_tracking_fragment_and_slash_is_the_existing_job(
    world: World,
) -> None:
    first = world.add(world.alice, text="one", url="https://acme.com/jobs/1")
    again = world.add(
        world.alice,
        text="other text",
        url="https://ACME.com/jobs/1/?utm_source=mail#apply",
    )
    assert again == AddedJob(first.job_number, AddOutcome.DUPLICATE)


def test_the_same_text_of_another_user_is_not_a_duplicate(world: World) -> None:
    world.add(world.alice)
    assert world.add(world.bob).outcome is AddOutcome.CREATED


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        ({"text": ""}, ("text", "Встав текст опису вакансії.")),
        ({"text": "x" * 100_001}, ("text", "Опис задовгий: більше 100000 символів.")),
        (
            {"url": "example.com/job"},
            ("url", "Посилання має починатися з http:// або https://."),
        ),
    ],
)
def test_an_invalid_job_is_rejected_and_nothing_is_saved(
    world: World, fields: dict[str, str], problem: tuple[str, str]
) -> None:
    with pytest.raises(InvalidFields) as caught:
        world.add(world.alice, **fields)
    assert [(p.field, p.message) for p in caught.value.problems] == [problem]
    assert world.listed(world.alice) == []


def test_a_linkedin_link_adds_the_text_to_the_waiting_job(world: World) -> None:
    waiting = world.seed_alert(world.alice, title="Backend Dev", company="Acme")
    added = world.add(
        world.alice, text=POSTING, url=ALERT_LINK, title="Other", company="Other"
    )
    assert added == AddedJob(waiting, AddOutcome.TEXT_ADDED)
    assert not added.duplicate
    job = world.get(world.alice, waiting)
    assert (job.text, job.needs_text) == (POSTING, False)
    assert (job.title, job.company) == ("Backend Dev", "Acme")
    assert job.url == "https://www.linkedin.com/jobs/view/4012345678"
    assert job.source == "linkedin_alert"
    assert len(world.listed(world.alice)) == 1


def test_the_added_text_makes_the_job_a_duplicate_of_that_text(world: World) -> None:
    waiting = world.seed_alert(world.alice, title="Backend Dev", company="Acme")
    world.add(world.alice, text=POSTING, url=ALERT_LINK)
    assert world.add(world.alice, text=POSTING) == AddedJob(
        waiting, AddOutcome.DUPLICATE
    )


def test_a_linkedin_link_to_a_job_with_text_changes_nothing(world: World) -> None:
    waiting = world.seed_alert(world.alice, title="Backend Dev", company="Acme")
    world.add(world.alice, text=POSTING, url=ALERT_LINK)
    again = world.add(world.alice, text="A different description", url=ALERT_LINK)
    assert again == AddedJob(waiting, AddOutcome.DUPLICATE)
    assert world.get(world.alice, waiting).text == POSTING


def test_a_text_that_exists_in_another_job_makes_that_job_the_duplicate(
    world: World,
) -> None:
    waiting = world.seed_alert(world.alice, title="Backend Dev", company="Acme")
    other = world.add(world.alice, text=POSTING)
    added = world.add(world.alice, text=POSTING, url=ALERT_LINK)
    assert added == AddedJob(other.job_number, AddOutcome.DUPLICATE)
    assert world.get(world.alice, waiting).needs_text is True


def test_a_linkedin_link_without_a_waiting_job_creates_a_job(world: World) -> None:
    added = world.add(world.alice, url=ALERT_LINK)
    assert added.outcome is AddOutcome.CREATED
    assert world.get(world.alice, added.job_number).url == (
        "https://www.linkedin.com/jobs/view/4012345678"
    )


def test_another_users_waiting_job_is_not_touched(world: World) -> None:
    waiting = world.seed_alert(world.alice, title="Backend Dev", company="Acme")
    added = world.add(world.bob, text=POSTING, url=ALERT_LINK)
    assert added.outcome is AddOutcome.CREATED
    assert world.get(world.alice, waiting).needs_text is True


def test_a_missing_job_is_not_found(world: World) -> None:
    with pytest.raises(NotFound):
        world.get(world.alice, 1)


def test_a_job_of_another_user_is_not_found(world: World) -> None:
    added = world.add(world.alice)
    with pytest.raises(NotFound):
        world.get(world.bob, added.job_number)


def test_newer_jobs_come_first_and_waiting_ones_last(world: World) -> None:
    old = world.add(world.alice, text="old").job_number
    waiting = world.seed_alert(world.alice, title="Dev", company="Acme")
    world.clock.advance(timedelta(days=1))
    new = world.add(world.alice, text="new").job_number
    assert world.numbers(world.alice) == [new, old, waiting]


def test_a_summary_has_the_list_fields(world: World) -> None:
    world.add(world.alice, url="https://acme.com/1", title="Dev", company="Acme")
    assert world.listed(world.alice) == [
        JobSummaryData(
            job_number=1,
            source="manual",
            url="https://acme.com/1",
            title="Dev",
            company="Acme",
            created_at=world.clock.now(),
            needs_text=False,
            dismissed=False,
        )
    ]


def test_the_query_looks_in_title_company_and_text_ignoring_case(world: World) -> None:
    by_title = world.add(world.alice, text="a", title="Rust Engineer").job_number
    by_company = world.add(world.alice, text="b", company="RUSTACEAN Ltd").job_number
    by_text = world.add(world.alice, text="we use rust daily").job_number
    world.add(world.alice, text="python only")
    assert sorted(world.numbers(world.alice, query="rust")) == [
        by_title,
        by_company,
        by_text,
    ]


def test_the_freshness_filter_keeps_recent_jobs(world: World) -> None:
    old = world.add(world.alice, text="old").job_number
    world.clock.advance(timedelta(days=10))
    new = world.add(world.alice, text="new").job_number
    assert world.numbers(world.alice, days="7") == [new]
    assert sorted(world.numbers(world.alice, days="30")) == [old, new]


def test_the_source_filter_and_the_source_list(world: World) -> None:
    manual = world.add(world.alice, text="a").job_number
    alert = world.seed_alert(world.alice, title="Dev", company="Acme")
    assert world.numbers(world.alice, source="linkedin_alert") == [alert]
    assert world.numbers(world.alice, source="manual") == [manual]
    assert world.portal.call(world.use_cases.job_sources, world.alice) == [
        "linkedin_alert",
        "manual",
    ]
    assert world.portal.call(world.use_cases.job_sources, world.bob) == []


def test_the_needs_text_filter_keeps_only_waiting_jobs(world: World) -> None:
    world.add(world.alice, text="a")
    waiting = world.seed_alert(world.alice, title="Dev", company="Acme")
    assert world.numbers(world.alice, needs_text=True) == [waiting]
    assert world.listed(world.alice, needs_text=True)[0].needs_text is True


def test_the_limit_cuts_the_list(world: World) -> None:
    for i in range(3):
        world.add(world.alice, text=f"job {i}")
    assert len(world.listed(world.alice, limit=2)) == 2


def test_invalid_filters_are_rejected(world: World) -> None:
    with pytest.raises(InvalidFields):
        world.listed(world.alice, days="0")


def test_the_list_shows_only_own_jobs(world: World) -> None:
    world.add(world.alice, text="alice's")
    assert world.listed(world.bob) == []


def test_dismissed_jobs_leave_the_list_and_show_with_the_flag(world: World) -> None:
    keep = world.add(world.alice, text="keep").job_number
    gone = world.add(world.alice, text="gone").job_number
    world.dismiss(world.alice, [gone], "не цікаво")
    assert world.numbers(world.alice) == [keep]
    assert world.numbers(world.alice, dismissed=True) == [gone]
    assert world.listed(world.alice, dismissed=True)[0].dismissed is True
    job = world.get(world.alice, gone)
    assert (job.dismissed_at, job.dismiss_reason) == (world.clock.now(), "не цікаво")


def test_a_batch_dismisses_every_job(world: World) -> None:
    numbers = [world.add(world.alice, text=f"j{i}").job_number for i in range(3)]
    world.dismiss(world.alice, numbers, "  не   підходить ")
    assert world.numbers(world.alice) == []
    assert world.get(world.alice, 2).dismiss_reason == "не підходить"


def test_dismissing_again_keeps_the_first_reason_and_time(world: World) -> None:
    number = world.add(world.alice).job_number
    world.dismiss(world.alice, [number], "перша причина")
    first_time = world.clock.now()
    world.clock.advance(timedelta(hours=1))
    world.dismiss(world.alice, [number], "друга причина")
    job = world.get(world.alice, number)
    assert (job.dismissed_at, job.dismiss_reason) == (first_time, "перша причина")


@pytest.mark.parametrize(
    ("numbers", "message"),
    [
        ([], "Порожня пачка: потрібна хоч одна вакансія."),
        (list(range(1, 52)), "У пачці не більше 50 вакансій."),
        ([99], "Вакансію 99 не знайдено."),
        ([1, 99], "Елемент 2: вакансію 99 не знайдено."),
        ([1, 1], "Елемент 2: вакансія 1 уже є в елементі 1."),
    ],
)
def test_an_invalid_batch_is_an_error_and_hides_nothing(
    world: World, numbers: list[int], message: str
) -> None:
    world.add(world.alice, text="one")
    with pytest.raises(InvalidValue) as caught:
        world.dismiss(world.alice, numbers)
    assert (caught.value.field, caught.value.message) == ("job_ids", message)
    assert world.numbers(world.alice) == [1]


def test_a_job_of_another_user_cannot_be_dismissed(world: World) -> None:
    number = world.add(world.alice).job_number
    with pytest.raises(InvalidValue):
        world.dismiss(world.bob, [number])
    assert world.numbers(world.alice) == [number]


@pytest.mark.parametrize(
    ("reason", "message"),
    [
        ("", "Вкажи причину приховування."),
        ("x" * 201, "Причина задовга: більше 200 символів."),
    ],
)
def test_a_bad_reason_is_an_error_and_hides_nothing(
    world: World, reason: str, message: str
) -> None:
    number = world.add(world.alice).job_number
    with pytest.raises(InvalidValue) as caught:
        world.dismiss(world.alice, [number], reason)
    assert (caught.value.field, caught.value.message) == ("reason", message)
    assert world.numbers(world.alice) == [number]


def test_a_restored_job_is_back_in_the_list(world: World) -> None:
    number = world.add(world.alice).job_number
    world.dismiss(world.alice, [number])
    world.restore(world.alice, number)
    assert world.numbers(world.alice) == [number]
    job = world.get(world.alice, number)
    assert (job.dismissed_at, job.dismiss_reason) == (None, None)


def test_restoring_a_job_that_is_not_dismissed_changes_nothing(world: World) -> None:
    number = world.add(world.alice).job_number
    before = world.get(world.alice, number)
    world.restore(world.alice, number)
    assert world.get(world.alice, number) == before


def test_restoring_a_missing_or_foreign_job_is_not_found(world: World) -> None:
    number = world.add(world.alice).job_number
    with pytest.raises(NotFound) as caught:
        world.restore(world.bob, number)
    assert caught.value.message == "Вакансію 1 не знайдено."
    with pytest.raises(NotFound):
        world.restore(world.alice, 99)


def test_the_number_of_a_dismissed_job_is_not_reused(world: World) -> None:
    world.add(world.alice, text="one")
    world.dismiss(world.alice, [1])
    assert world.add(world.alice, text="two").job_number == 2
