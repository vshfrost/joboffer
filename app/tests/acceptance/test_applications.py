"""Кроки для features/applications_*.feature: use cases подач і вакансій + in-memory адаптери.

Значення в кроках — у лапках. Користувачі — «Богдан» і «Наталя» (два актори спільного світу подач).
Номер вакансії — `job_id` користувача, лічильник на користувача. Дії записують помилку домену
для кроків «Тоді»; «Припустимо я позначив …» додатково вимагає, щоб дія вдалася.
"""

import functools
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.actor import Actor
from application.contracts.applications import ApplicationData
from application.contracts.jobs import JobSearchInput, JobSummaryData
from domain.shared.errors import DomainError, InvalidFields, InvalidValue
from tests.support.applications import ApplicationWorld
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds

scenarios(
    "features/applications_mark.feature",
    "features/applications_status.feature",
    "features/applications_jobs.feature",
    "features/applications_users.feature",
)

Step = Callable[..., Any]
NO_APPLICATION = "-"


def rx(pattern: str) -> Any:
    return parsers.re(pattern)


def succeeded(step: Step) -> Step:
    """Крок-передумова: дія має вдатися, інакше сценарій не про те."""

    @functools.wraps(step)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        step(*args, **kwargs)
        world: World = kwargs["world"]
        assert world.error is None, world.error

    return wrapper


def action(pattern: str) -> Callable[[Step], Step]:
    """Один текст — і «Припустимо я позначив …», і «Якщо я позначаю …» (`(?:позначаю|позначив)`)."""

    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(succeeded(step))
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.core = ApplicationWorld(portal, clock, ids)
        self.actors = {"Богдан": self.core.alice, "Наталя": self.core.bob}
        self.actor: Actor = self.core.alice
        self.error: DomainError | None = None
        self.last_list: list[JobSummaryData] | None = None

    def become(self, name: str) -> None:
        self.actor = self.actors[name]
        self.reset_outcome()

    def reset_outcome(self) -> None:
        self.error = None
        self.last_list = None

    def attempt(self, call: Callable[[], Any]) -> Any:
        """Виконує дію; помилка домену запамʼятовується для кроків «Тоді»."""
        self.reset_outcome()
        try:
            return call()
        except DomainError as error:
            self.error = error
            return None

    def mark(self, job: int, **fields: Any) -> None:
        self.attempt(lambda: self.core.mark(self.actor, job, **fields))

    def move(self, job: int, status: str) -> None:
        self.attempt(lambda: self.core.move(self.actor, job, status))

    def application(self, job: int) -> ApplicationData | None:
        return self.core.application(self.actor, job)

    def present(self, job: int) -> ApplicationData:
        found = self.application(job)
        assert found is not None, f"подачі на вакансію {job} нема"
        return found

    def search(self, **fields: Any) -> None:
        data = JobSearchInput(**fields)
        self.last_list = self.attempt(
            lambda: self.core.portal.call(self.core.jobs.list_jobs, self.actor, data)
        )

    def current_list(self) -> list[JobSummaryData]:
        if self.last_list is None:
            self.search()
        assert self.last_list is not None, self.error
        return self.last_list

    def problems(self) -> dict[str, str]:
        assert isinstance(self.error, InvalidFields), self.error
        return {problem.field: problem.message for problem in self.error.problems}


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def shown(text: str) -> list[str]:
    return [] if text.strip() == "" else [part.strip() for part in text.split(";")]


def numbers(text: str) -> list[int]:
    return [int(part) for part in shown(text)]


# --- хто я, час, передумови -----------------------------------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_given(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@bdd_given(rx(r"^минає (?P<hours>\d+) год (?P<minutes>\d+) хв$"))
@bdd_when(rx(r"^минає (?P<hours>\d+) год (?P<minutes>\d+) хв$"))
def time_passes(world: World, hours: str, minutes: str) -> None:
    world.core.clock.advance(timedelta(hours=int(hours), minutes=int(minutes)))


@bdd_given(rx(r'^в UTC зараз "(?P<moment>\d{4}-\d\d-\d\d \d\d:\d\d)"$'))
def clock_is(world: World, moment: str) -> None:
    target = datetime.strptime(moment, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    world.core.clock.advance(target - world.core.clock.now())


@bdd_given(rx(r'^я додав вакансію "(?P<text>[^"]*)"$'))
@bdd_when(rx(r'^я додав вакансію "(?P<text>[^"]*)"$'))
def add_job(world: World, text: str) -> None:
    world.core.add_job(world.actor, text)
    world.reset_outcome()


@bdd_given(rx(r'^є вакансії зі статусами подач: "(?P<statuses>[^"]*)"$'))
def jobs_with_statuses(world: World, statuses: str) -> None:
    """Вакансії по одній на статус (`-` — без подачі), з інтервалом у хвилину: новіші мають більший номер."""
    for position, status in enumerate(shown(statuses)):
        job = world.core.add_job(world.actor, f"Вакансія {position + 1}")
        world.core.clock.advance(timedelta(minutes=1))
        if status != NO_APPLICATION:
            world.core.mark(world.actor, job)
            if status != "applied":
                world.core.move(world.actor, job, status)
    world.reset_outcome()


@bdd_given(rx(r'^подача на вакансію (?P<job>\d+) у статусі "(?P<status>[^"]*)"$'))
def application_in_status(world: World, job: str, status: str) -> None:
    """Вакансія вже подана (передумова сценарію); тут лише переводимо її у потрібний статус."""
    if status != "applied":
        world.core.move(world.actor, int(job), status)
    world.reset_outcome()


# --- подача: позначити, рухати -----------------------------------------------------------


@action(
    r"^я (?:позначаю|позначив) вакансію (?P<job>\d+) поданою: канал \"(?P<channel>[^\"]*)\","
    r' дата "(?P<day>[^"]*)", ATS "(?P<ats>[^"]*)", домени "(?P<domains>[^"]*)",'
    r' адреси "(?P<emails>[^"]*)"$'
)
def mark_full(
    world: World,
    job: str,
    channel: str,
    day: str,
    ats: str,
    domains: str,
    emails: str,
) -> None:
    world.mark(
        int(job),
        channel=channel,
        applied_on=day,
        ats=ats,
        company_domains=shown(domains),
        company_emails=shown(emails),
    )


@action(
    r'^я (?:позначаю|позначив) вакансію (?P<job>\d+) поданою каналом "(?P<channel>[^"]*)"$'
)
def mark_channel(world: World, job: str, channel: str) -> None:
    world.mark(int(job), channel=channel)


@action(
    r"^я (?:позначаю|позначив) вакансію (?P<job>\d+) поданою з (?P<count>\d+) доменами$"
)
def mark_many_domains(world: World, job: str, count: str) -> None:
    world.mark(
        int(job),
        channel="email",
        company_domains=[f"company{n}.example.com" for n in range(int(count))],
    )


@action(
    r'^я (?:перевожу|перевів) подачу на вакансію (?P<job>\d+) у статус "(?P<status>[^"]*)"$'
)
def move_application(world: World, job: str, status: str) -> None:
    world.move(int(job), status)


@action(
    r'^я (?:ховаю|сховав) вакансії "(?P<ids>[^"]*)" з причиною "(?P<reason>[^"]*)"$'
)
def dismiss_ids(world: World, ids: str, reason: str) -> None:
    world.attempt(
        lambda: world.core.portal.call(
            world.core.jobs.dismiss_jobs, world.actor, numbers(ids), reason
        )
    )


@bdd_given(rx(r'^я сховав вакансію (?P<job>\d+) з причиною "(?P<reason>[^"]*)"$'))
def dismissed_one(world: World, job: str, reason: str) -> None:
    world.core.portal.call(
        world.core.jobs.dismiss_jobs, world.actor, [int(job)], reason
    )
    world.reset_outcome()


# --- подача: перевірки --------------------------------------------------------------------


APPLICATION_FIELDS = (
    r' статус "(?P<status>[^"]*)", канал "(?P<channel>[^"]*)",'
    r' дата "(?P<day>[^"]*)", ATS "(?P<ats>[^"]*)", домени "(?P<domains>[^"]*)",'
    r' адреси "(?P<emails>[^"]*)"$'
)


def check_application(
    world: World,
    job: str,
    status: str,
    channel: str,
    day: str,
    ats: str,
    domains: str,
    emails: str,
) -> None:
    found = world.present(int(job))
    assert (
        found.status.value,
        found.channel.value,
        found.applied_on.isoformat(),
        found.ats.value if found.ats else "",
        list(found.company_domains),
        list(found.company_emails),
    ) == (status, channel, day, ats, shown(domains), shown(emails))


@bdd_then(rx(r"^подача на вакансію (?P<job>\d+):" + APPLICATION_FIELDS))
def application_is(
    world: World,
    job: str,
    status: str,
    channel: str,
    day: str,
    ats: str,
    domains: str,
    emails: str,
) -> None:
    assert world.error is None, world.error
    check_application(world, job, status, channel, day, ats, domains, emails)


@bdd_then(rx(r"^подача на вакансію (?P<job>\d+) лишилась:" + APPLICATION_FIELDS))
def application_unchanged(
    world: World,
    job: str,
    status: str,
    channel: str,
    day: str,
    ats: str,
    domains: str,
    emails: str,
) -> None:
    check_application(world, job, status, channel, day, ats, domains, emails)


@bdd_then(rx(r"^подача на вакансію (?P<job>\d+) має (?P<count>\d+) доменів$"))
def application_domain_count(world: World, job: str, count: str) -> None:
    assert world.error is None, world.error
    assert len(world.present(int(job)).company_domains) == int(count)


@bdd_then(rx(r"^подачі на вакансію (?P<job>\d+) нема$"))
def no_application(world: World, job: str) -> None:
    assert world.application(int(job)) is None


@bdd_then(rx(r'^статус подачі на вакансію (?P<job>\d+) — "(?P<status>[^"]*)"$'))
def application_status(world: World, job: str, status: str) -> None:
    assert world.present(int(job)).status.value == status


@bdd_then(rx(r'^статус подачі на вакансію (?P<job>\d+) змінено "(?P<moment>[^"]*)"$'))
def status_changed_at(world: World, job: str, moment: str) -> None:
    assert world.present(int(job)).status_changed_at.isoformat() == moment


@bdd_then(
    rx(r'^з подачі на вакансію (?P<job>\d+) можна перейти у: "(?P<statuses>[^"]*)"$')
)
def transitions(world: World, job: str, statuses: str) -> None:
    allowed = [status.value for status in world.present(int(job)).allowed_transitions]
    assert allowed == shown(statuses)


# --- вакансії: деталі, список, приховування ---------------------------------------------------


@bdd_then(rx(r"^у вакансії (?P<job>\d+) нема подачі$"))
def job_without_application(world: World, job: str) -> None:
    assert world.core.job(world.actor, int(job)).application is None


@bdd_then(
    rx(
        r'^у вакансії (?P<job>\d+) подача зі статусом "(?P<status>[^"]*)" і каналом "(?P<channel>[^"]*)"$'
    )
)
def job_with_application(world: World, job: str, status: str, channel: str) -> None:
    application = world.core.job(world.actor, int(job)).application
    assert application is not None
    assert (application.status.value, application.channel.value) == (status, channel)


@bdd_then(rx(r"^вакансія (?P<job>\d+) не схована$"))
def not_dismissed(world: World, job: str) -> None:
    found = world.core.job(world.actor, int(job))
    assert (found.dismissed_at, found.dismiss_reason) == (None, None)


@bdd_then(rx(r'^вакансія (?P<job>\d+) схована з причиною "(?P<reason>[^"]*)"$'))
def dismissed_with(world: World, job: str, reason: str) -> None:
    found = world.core.job(world.actor, int(job))
    assert found.dismissed_at is not None
    assert found.dismiss_reason == reason


@bdd_when(rx(r"^я переглядаю список без фільтрів$"))
def list_all(world: World) -> None:
    world.search()


@bdd_when(rx(r'^я переглядаю список зі статусом "(?P<status>[^"]*)"$'))
def list_by_status(world: World, status: str) -> None:
    world.search(status=status)


@bdd_when(
    rx(
        r'^я переглядаю список зі статусом "(?P<status>[^"]*)" і запитом "(?P<query>[^"]*)"$'
    )
)
def list_by_status_and_query(world: World, status: str, query: str) -> None:
    world.search(status=status, query=query)


@bdd_then(rx(r'^номери в списку за порядком: "(?P<order>[^"]*)"$'))
def list_order(world: World, order: str) -> None:
    assert [item.job_number for item in world.current_list()] == numbers(order)


@bdd_then(rx(r"^у списку вакансія (?P<job>\d+) без статусу$"))
def list_row_without_status(world: World, job: str) -> None:
    row = next(i for i in world.current_list() if i.job_number == int(job))
    assert row.status is None


@bdd_then(rx(r'^у списку вакансія (?P<job>\d+) має статус "(?P<status>[^"]*)"$'))
def list_row_status(world: World, job: str, status: str) -> None:
    row = next(i for i in world.current_list() if i.job_number == int(job))
    assert row.status is not None
    assert row.status.value == status


# --- помилки ----------------------------------------------------------------------------------


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)"$'))
def error_code(world: World, code: str) -> None:
    assert world.error is not None, "помилки не було"
    assert world.error.code == code


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def error_message(world: World, code: str, message: str) -> None:
    assert world.error is not None, "помилки не було"
    assert (world.error.code, world.error.message) == (code, message)


@bdd_then(
    rx(
        r'^отримую помилку "(?P<code>[^"]*)" для поля "(?P<field>[^"]*)" з текстом "(?P<message>[^"]*)"$'
    )
)
def error_field_message(world: World, code: str, field: str, message: str) -> None:
    error = world.error
    assert isinstance(error, InvalidValue), error
    assert (error.code, error.field, error.message) == (code, field, message)


@bdd_then(rx(r'^помилка поля "(?P<field>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def field_problem(world: World, field: str, message: str) -> None:
    assert world.problems()[field] == message


@bdd_then(rx(r'^помилки полів: "(?P<fields>[^"]*)"$'))
def field_problems(world: World, fields: str) -> None:
    assert list(world.problems()) == shown(fields)
