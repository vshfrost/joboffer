"""Кроки для features/jobs_*.feature: use cases вакансій + in-memory адаптери через портал.

Усі значення в кроках — у лапках і можуть бути порожніми, тому кроки — регулярні вирази з
іменованими групами. «Припустимо я додав …» і «Якщо я додаю …» — один і той самий крок; у
«Припустимо» додатково перевіряється, що дія вдалася. Номер вакансії — `job_id`, лічильник
на користувача; внутрішній UUID у сценаріях не фігурує.
"""

import functools
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

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
from domain.jobs.linkedin import linkedin_job_url
from domain.shared.errors import DomainError, InvalidFields, InvalidValue
from domain.shared.local_time import local_day
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store

scenarios(
    "features/jobs_add.feature",
    "features/jobs_linkedin.feature",
    "features/jobs_view.feature",
    "features/jobs_list.feature",
    "features/jobs_dismiss.feature",
    "features/jobs_users.feature",
)

Step = Callable[..., Any]


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
    """Один текст — і «Припустимо я додав …», і «Якщо я додаю …» (дієслово в `(?:додаю|додав)`)."""

    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(succeeded(step))
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.store = Store.empty()
        self.use_cases = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.store), clock, ids
        )
        self.actors: dict[str, Actor] = {}
        self.current = ""
        self.added: AddedJob | None = None
        self.error: DomainError | None = None
        self.last_list: list[JobSummaryData] | None = None

    def become(self, name: str) -> None:
        if name not in self.actors:
            self.actors[name] = Actor(
                user_id=UserId(self.ids.new()),
                channel=Channel.WEB,
                client_id="web",
                grant_id=None,
                scopes=frozenset(Scope),
                correlation_id="test",
            )
        self.current = name
        self.reset_outcome()

    @property
    def actor(self) -> Actor:
        return self.actors[self.current]

    def reset_outcome(self) -> None:
        self.added = None
        self.error = None
        self.last_list = None

    def attempt(self, call: Callable[[], Any]) -> Any:
        """Виконує дію; помилка домену запамʼятовується для кроків «Тоді»."""
        self.reset_outcome()
        try:
            return self.portal.call(call)
        except DomainError as error:
            self.error = error
            return None

    def add(self, **fields: str) -> None:
        data = JobInput(**fields)
        self.added = self.attempt(lambda: self.use_cases.add_job(self.actor, data))

    def dismiss(self, numbers: list[int], reason: str) -> None:
        self.attempt(lambda: self.use_cases.dismiss_jobs(self.actor, numbers, reason))

    def search(self, **fields: Any) -> None:
        data = JobSearchInput(**fields)
        self.last_list = self.attempt(
            lambda: self.use_cases.list_jobs(self.actor, data)
        )

    def current_list(self) -> list[JobSummaryData]:
        """Результат останнього перегляду; якщо його не було — звичайний список без фільтрів."""
        if self.last_list is None:
            self.last_list = self.portal.call(
                self.use_cases.list_jobs, self.actor, JobSearchInput()
            )
        return self.last_list

    def job(self, number: int) -> JobData:
        """Вакансія, як її бачить поточний користувач (без запису в результат кроку)."""
        return self.portal.call(self.use_cases.get_job, self.actor, number)

    def seed_alert(self, title: str, company: str, linkedin_id: str) -> None:
        """Вакансія з листа-алерту LinkedIn без тексту: її створить B10, тут — передумова."""

        async def seed() -> None:
            async with InMemoryJobUnitOfWork(self.store) as uow:
                await uow.jobs.add(
                    self.actor.user_id,
                    JobId(self.ids.new()),
                    NewJob(
                        text=None,
                        url=linkedin_job_url(linkedin_id),
                        title=title,
                        company=company,
                        linkedin_id=linkedin_id,
                        source="linkedin_alert",
                    ),
                    self.clock.now(),
                )
                await uow.commit()

        self.portal.call(seed)

    def problems(self) -> dict[str, str]:
        assert isinstance(self.error, InvalidFields), self.error
        return {problem.field: problem.message for problem in self.error.problems}


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def numbers(text: str) -> list[int]:
    return [] if text.strip() == "" else [int(part) for part in text.split(";")]


def shown(text: str) -> list[str]:
    return [] if text == "" else [part.strip() for part in text.split(";")]


# --- хто я, час, передумови -----------------------------------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@bdd_given(rx(r"^минає (?P<hours>\d+) год (?P<minutes>\d+) хв$"))
@bdd_when(rx(r"^минає (?P<hours>\d+) год (?P<minutes>\d+) хв$"))
def time_passes(world: World, hours: str, minutes: str) -> None:
    world.clock.advance(timedelta(hours=int(hours), minutes=int(minutes)))


@bdd_given(rx(r"^минає (?P<days>\d+) (?:доба|діб)$"))
@bdd_when(rx(r"^минає (?P<days>\d+) (?:доба|діб)$"))
def days_pass(world: World, days: str) -> None:
    world.clock.advance(timedelta(days=int(days)))


@bdd_given(
    rx(
        r'^є вакансія з листа-алерту "(?P<title>[^"]*)" компанії "(?P<company>[^"]*)"'
        r" з посиланням LinkedIn (?P<linkedin_id>\d+)$"
    )
)
def alert_job(world: World, title: str, company: str, linkedin_id: str) -> None:
    world.seed_alert(title, company, linkedin_id)


@bdd_given(rx(r"^є ще (?P<count>\d+) вакансій$"))
def more_jobs(world: World, count: str) -> None:
    for number in range(int(count)):
        world.add(text=f"Додаткова вакансія {number}")
        assert world.error is None, world.error


# --- додавання ------------------------------------------------------------------------------


@action(
    r'^я (?:додаю|додав) вакансію з текстом "(?P<text>[^"]*)", посиланням "(?P<url>[^"]*)",'
    r' назвою "(?P<title>[^"]*)", компанією "(?P<company>[^"]*)"$'
)
def add_full(world: World, text: str, url: str, title: str, company: str) -> None:
    world.add(text=text, url=url, title=title, company=company)


@action(r'^я (?:додаю|додав) вакансію з текстом "(?P<text>[^"]*)"$')
def add_text(world: World, text: str) -> None:
    world.add(text=text)


@action(r"^я (?:додаю|додав) вакансію з порожнім текстом$")
def add_empty(world: World) -> None:
    world.add(text="")


@action(
    r'^я (?:додаю|додав) вакансію з порожнім текстом і посиланням "(?P<url>[^"]*)"$'
)
def add_empty_with_url(world: World, url: str) -> None:
    world.add(text="", url=url)


@action(r"^я (?:додаю|додав) вакансію з текстом із (?P<length>\d+) символів$")
def add_long(world: World, length: str) -> None:
    world.add(text="x" * int(length))


@action(r"^я (?:додаю|додав) вакансію з текстом із (?P<length>\d+) пробілів$")
def add_blank(world: World, length: str) -> None:
    world.add(text=" " * int(length))


@bdd_then(rx(r"^вакансія додана з номером (?P<number>\d+)$"))
def created(world: World, number: str) -> None:
    assert world.error is None, world.error
    assert world.added == AddedJob(int(number), AddOutcome.CREATED)


@bdd_then(rx(r"^це дубль вакансії (?P<number>\d+)$"))
def duplicate(world: World, number: str) -> None:
    assert world.error is None, world.error
    assert world.added == AddedJob(int(number), AddOutcome.DUPLICATE)
    assert world.added.duplicate is True


@bdd_then(rx(r"^до вакансії (?P<number>\d+) дописано текст$"))
def text_added(world: World, number: str) -> None:
    assert world.error is None, world.error
    assert world.added == AddedJob(int(number), AddOutcome.TEXT_ADDED)
    assert world.added.duplicate is False


# --- вакансія ---------------------------------------------------------------------------------


@bdd_when(rx(r"^я відкриваю вакансію (?P<number>-?\d+)$"))
def open_job(world: World, number: str) -> None:
    world.attempt(lambda: world.use_cases.get_job(world.actor, int(number)))


@bdd_then(rx(r'^вакансія (?P<number>\d+) має текст "(?P<text>[^"]*)"$'))
def has_text(world: World, number: str, text: str) -> None:
    assert world.job(int(number)).text == text


@bdd_then(rx(r"^вакансія (?P<number>\d+) не має тексту$"))
def has_no_text(world: World, number: str) -> None:
    assert world.job(int(number)).text is None


@bdd_then(rx(r"^вакансія (?P<number>\d+) потребує тексту$"))
def needs_text(world: World, number: str) -> None:
    assert world.job(int(number)).needs_text is True


@bdd_then(rx(r"^вакансія (?P<number>\d+) не потребує тексту$"))
def needs_no_text(world: World, number: str) -> None:
    assert world.job(int(number)).needs_text is False


@bdd_then(rx(r'^вакансія (?P<number>\d+) має джерело "(?P<source>[^"]*)"$'))
def has_source(world: World, number: str, source: str) -> None:
    assert world.job(int(number)).source == source


@bdd_then(rx(r"^вакансія (?P<number>\d+) без назви, компанії й посилання$"))
def has_no_details(world: World, number: str) -> None:
    job = world.job(int(number))
    assert (job.title, job.company, job.url) == (None, None, None)


@bdd_then(
    rx(
        r'^вакансія (?P<number>\d+) має назву "(?P<title>[^"]*)", компанію "(?P<company>[^"]*)"'
        r' і посилання "(?P<url>[^"]*)"$'
    )
)
def has_details(world: World, number: str, title: str, company: str, url: str) -> None:
    job = world.job(int(number))
    assert (job.title, job.company, job.url) == (title, company, url)


@bdd_then(rx(r'^вакансія (?P<number>\d+) має посилання "(?P<url>[^"]*)"$'))
def has_url(world: World, number: str, url: str) -> None:
    assert world.job(int(number)).url == url


@bdd_then(rx(r'^вакансія (?P<number>\d+) додана "(?P<moment>[^"]*)"$'))
def added_at(world: World, number: str, moment: str) -> None:
    assert world.job(int(number)).created_at.isoformat() == moment


@bdd_then(rx(r'^вакансія (?P<number>\d+) додана в день "(?P<day>[^"]*)" за Мадридом$'))
def added_day(world: World, number: str, day: str) -> None:
    assert local_day(world.job(int(number)).created_at) == day


@bdd_then(rx(r"^вакансія (?P<number>\d+) не схована$"))
def not_dismissed(world: World, number: str) -> None:
    job = world.job(int(number))
    assert (job.dismissed_at, job.dismiss_reason) == (None, None)


@bdd_then(rx(r"^вакансія (?P<number>\d+) без причини приховування$"))
def no_reason(world: World, number: str) -> None:
    assert world.job(int(number)).dismiss_reason is None


@bdd_then(rx(r'^вакансія (?P<number>\d+) схована з причиною "(?P<reason>[^"]*)"$'))
def dismissed_with(world: World, number: str, reason: str) -> None:
    job = world.job(int(number))
    assert job.dismissed_at is not None
    assert job.dismiss_reason == reason


@bdd_then(rx(r'^вакансія (?P<number>\d+) схована "(?P<moment>[^"]*)"$'))
def dismissed_at(world: World, number: str, moment: str) -> None:
    dismissed = world.job(int(number)).dismissed_at
    assert dismissed is not None
    assert dismissed.isoformat() == moment


# --- список -----------------------------------------------------------------------------------

FILTERS = (
    r'^я переглядаю список: пошук "(?P<query>[^"]*)", свіжість "(?P<days>[^"]*)", '
    r'джерело "(?P<source>[^"]*)", лише без тексту "(?P<waiting>так|ні)", '
    r'лише сховані "(?P<hidden>так|ні)", ліміт (?P<limit>-?\d+)$'
)


@bdd_when(rx(r"^я переглядаю список без фільтрів$"))
def list_all(world: World) -> None:
    world.search()


@bdd_when(rx(FILTERS))
def list_filtered(
    world: World,
    query: str,
    days: str,
    source: str,
    waiting: str,
    hidden: str,
    limit: str,
) -> None:
    world.search(
        query=query,
        days=days,
        source=source,
        needs_text=waiting == "так",
        dismissed=hidden == "так",
        limit=int(limit),
    )


@bdd_when(rx(r"^я переглядаю список із запитом із (?P<length>\d+) символів$"))
def list_long_query(world: World, length: str) -> None:
    world.search(query="q" * int(length))


@bdd_then(rx(r"^у списку (?P<count>\d+) вакансі\w+$"))
def list_count(world: World, count: str) -> None:
    assert len(world.current_list()) == int(count)


@bdd_then(rx(r'^назви в списку за порядком: "(?P<titles>[^"]*)"$'))
def list_titles(world: World, titles: str) -> None:
    assert [item.title or "" for item in world.current_list()] == shown(titles)


@bdd_then(rx(r'^номери в списку: "(?P<numbers>[^"]*)"$'))
def list_numbers(world: World, numbers: str) -> None:
    assert sorted(item.job_number for item in world.current_list()) == sorted(
        int(part) for part in shown(numbers)
    )


@bdd_then(
    rx(
        r'^у списку вакансія (?P<number>\d+): назва "(?P<title>[^"]*)", компанія "(?P<company>[^"]*)", '
        r'посилання "(?P<url>[^"]*)", джерело "(?P<source>[^"]*)", '
        r"(?P<waiting>з|без) позначк\w+ «потрібен текст», (?P<hidden>не схована|схована)$"
    )
)
def list_row(
    world: World,
    number: str,
    title: str,
    company: str,
    url: str,
    source: str,
    waiting: str,
    hidden: str,
) -> None:
    row = next(item for item in world.current_list() if item.job_number == int(number))
    assert (row.title or "", row.company or "", row.url or "", row.source) == (
        title,
        company,
        url,
        source,
    )
    assert row.needs_text is (waiting == "з")
    assert row.dismissed is (hidden == "схована")
    assert world.clock.now() >= row.created_at


@bdd_then("джерел немає")
def no_sources(world: World) -> None:
    assert world.portal.call(world.use_cases.job_sources, world.actor) == []


@bdd_then(rx(r'^джерела: "(?P<sources>[^"]*)"$'))
def sources(world: World, sources: str) -> None:
    found = world.portal.call(world.use_cases.job_sources, world.actor)
    assert found == shown(sources)


# --- приховування й повернення --------------------------------------------------------------


@action(
    r'^я (?:ховаю|сховав) вакансії "(?P<ids>[^"]*)" з причиною "(?P<reason>[^"]*)"$'
)
def dismiss_ids(world: World, ids: str, reason: str) -> None:
    world.dismiss(numbers(ids), reason)


@action(
    r"^я (?:ховаю|сховав) вакансію (?P<number>\d+) з причиною \"(?P<reason>[^\"]*)\"$"
)
def dismiss_one(world: World, number: str, reason: str) -> None:
    world.dismiss([int(number)], reason)


@action(r'^я (?:ховаю|сховав) вакансії "(?P<ids>[^"]*)" з порожньою причиною$')
def dismiss_without_reason(world: World, ids: str) -> None:
    world.dismiss(numbers(ids), "")


@action(
    r"^я (?:ховаю|сховав) вакансію (?P<number>\d+) з причиною із (?P<length>\d+) символів$"
)
def dismiss_long_reason(world: World, number: str, length: str) -> None:
    world.dismiss([int(number)], "r" * int(length))


@action(
    r'^я (?:ховаю|сховав) вакансії з 1 по (?P<last>\d+) з причиною "(?P<reason>[^"]*)"$'
)
def dismiss_range(world: World, last: str, reason: str) -> None:
    world.dismiss(list(range(1, int(last) + 1)), reason)


@action(r"^я (?:повертаю|повернув) вакансію (?P<number>\d+)$")
def restore(world: World, number: str) -> None:
    world.attempt(lambda: world.use_cases.restore_job(world.actor, int(number)))


@bdd_then("приховування вдалося")
@bdd_then("повернення вдалося")
def operation_succeeded(world: World) -> None:
    assert world.error is None, world.error


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


@bdd_then(rx(r"^кількість помилок полів — (?P<count>\d+)$"))
def problem_count(world: World, count: str) -> None:
    assert len(world.problems()) == int(count)
