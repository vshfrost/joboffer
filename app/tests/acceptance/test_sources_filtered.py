"""Кроки для features/sources_filtered.feature: вакансії з джерел, які вже не проходять фільтр профілю, і
приховування вибраних. Use cases й in-memory адаптери, без мережі й бази.

Вакансії «у мене» / «у "Наталя"» створюються напряму в сховищі з джерелом, локацією й текстом, які задає сценарій;
вакансія в кроках названа своєю назвою (вона унікальна в сценарії). Профіль збирається кроками «у моєму
профілі …». Що користувач бачив у списку, запам'ятовується: «ховаю усе, що бачив» повторює вибір з екрана
вже після змін. Помилки use case лягають у `world.error`."""

import functools
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.sources import SourcesOverview
from application.jobs.use_cases import JobUseCases
from application.sources.filtered import FilteredJobUseCases
from application.sources.overview import SourceOverviewUseCases
from domain.analysis.analysis import Analysis, JobAnalysis
from domain.applications.application import (
    Application,
    ApplicationChannel,
    ApplicationStatus,
)
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import Job, NewJob
from domain.profile.locations import SearchLocation
from domain.profile.modes import WorkMode
from domain.profile.profile import Profile
from domain.shared.errors import DomainError, InvalidValue
from domain.sources.filtered import FilteredJob
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork
from tests.support.source_overview import InMemorySourceOverviewUnitOfWork
from tests.support.source_runs import SourceRunStore

scenarios("features/sources_filtered.feature")

Step = Callable[..., Any]
FIELDS = r'(?P<fields>(?:,? (?:компанією|з текстом|з локацією) "[^"]*")*)'
FIELD = re.compile(r'(компанією|з текстом|з локацією) "([^"]*)"')
OWN = r'(?:у мене|у "(?P<user>[^"]*)")'


def rx(pattern: str) -> Any:
    return parsers.re(pattern)


def listed(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split(";") if part.strip())


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.store = SourceRunStore()
        self.overview = SourceOverviewUseCases(
            lambda: InMemorySourceOverviewUnitOfWork(self.store), clock
        )
        self.filtered = FilteredJobUseCases(
            lambda: InMemorySourceOverviewUnitOfWork(self.store), clock
        )
        self.jobs = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.store.jobs), clock, ids
        )
        self.actors: dict[str, Actor] = {}
        self.me = ""
        self.created = 0
        self.error: DomainError | None = None
        self.listing: list[FilteredJob] = []
        self.seen: list[int] = []
        self.dismissed: int | None = None

    def actor(self, name: str | None = None) -> Actor:
        return self.actors[name or self.me]

    def profile(self, name: str | None = None) -> Profile:
        return self.store.profiles.get(self.actor(name).user_id, Profile())

    def change_profile(self, profile: Profile, name: str | None = None) -> None:
        self.store.profiles[self.actor(name).user_id] = profile

    def seed_job(
        self, user: str, title: str, source: str, fields: str, company: str | None
    ) -> None:
        values = {
            "компанією": company,
            "з текстом": "Опис вакансії.",
            "з локацією": None,
        } | dict(FIELD.findall(fields))
        self.created += 1
        owner = self.actor(user).user_id

        async def seed() -> None:
            async with InMemoryJobUnitOfWork(self.store.jobs) as uow:
                await uow.jobs.add(
                    owner,
                    JobId(self.ids.new()),
                    NewJob(
                        text=values["з текстом"],
                        url=f"https://jobs.example/{self.created}",
                        title=title,
                        company=values["компанією"],
                        location=values["з локацією"],
                        source=source,
                    ),
                    self.clock.now(),
                )
                await uow.commit()

        self.portal.call(seed)

    def job_of(self, title: str, user: str | None = None) -> Job:
        owner = self.actor(user).user_id
        found = [
            job
            for (who, _), job in self.store.jobs.jobs.items()
            if who == owner and job.title == title
        ]
        assert len(found) == 1, f"у вакансіях «{title}»: {len(found)}"
        return found[0]

    def number_of(self, title: str) -> int:
        return self.job_of(title).number

    def view(self) -> list[FilteredJob]:
        self.listing = self.portal.call(self.filtered.list_filtered, self.actor())
        self.seen = [item.number for item in self.listing]
        return self.listing

    def hide(self, numbers: list[int]) -> None:
        self.error, self.dismissed = None, None
        try:
            self.dismissed = self.portal.call(
                self.filtered.dismiss_filtered, self.actor(), numbers
            )
        except DomainError as exc:
            self.error = exc

    def overview_now(self) -> SourcesOverview:
        return self.portal.call(self.overview.overview, self.actor())


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def succeeded(step: Step) -> Step:
    """Крок-передумова: дія має вдатися, інакше сценарій не про те."""

    @functools.wraps(step)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        step(*args, **kwargs)
        world: World = kwargs["world"]
        assert world.error is None, world.error

    return wrapper


# --- користувачі, профіль, вакансії -----------------------------------------------------------


@bdd_given(rx(r'^є користувачі "(?P<first>[^"]*)" та "(?P<second>[^"]*)"$'))
def users(world: World, first: str, second: str) -> None:
    for name in (first, second):
        world.actors[name] = Actor(
            user_id=UserId(world.ids.new()),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )


@bdd_given(rx(r'^я — користувач "(?P<user>[^"]*)"$'))
@bdd_given(rx(r'^я стаю користувачем "(?P<user>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<user>[^"]*)"$'))
def i_am(world: World, user: str) -> None:
    world.me = user
    world.error, world.dismissed, world.listing, world.seen = None, None, [], []


@bdd_given(
    rx(
        r'^у (?:моєму профілі|профілі "(?P<user>[^"]*)") слова назви "(?P<words>[^"]*)"$'
    )
)
@bdd_when(
    rx(
        r'^у (?:моєму профілі|профілі "(?P<user>[^"]*)") слова назви "(?P<words>[^"]*)"$'
    )
)
def profile_keywords(world: World, user: str | None, words: str) -> None:
    profile = world.profile(user)
    rules = replace(profile.rules, title_keywords=listed(words))
    world.change_profile(replace(profile, rules=rules), user)


@bdd_given(rx(r'^у моєму профілі виключені слова назви "(?P<words>[^"]*)"$'))
def profile_exclude(world: World, words: str) -> None:
    rules = replace(world.profile().rules, title_exclude=listed(words))
    world.change_profile(replace(world.profile(), rules=rules))


@bdd_given(rx(r'^у моєму профілі формати "(?P<modes>[^"]*)"$'))
def profile_modes(world: World, modes: str) -> None:
    locations = replace(
        world.profile().locations,
        work_modes=frozenset(WorkMode(mode) for mode in listed(modes)),
    )
    world.change_profile(replace(world.profile(), locations=locations))


@bdd_given(
    rx(
        r'^у моєму профілі місце "(?P<place>[^"]*)" із синонімами "(?P<aliases>[^"]*)"'
        r' і форматами "(?P<modes>[^"]*)"$'
    )
)
def profile_place(world: World, place: str, aliases: str, modes: str) -> None:
    found = SearchLocation(
        place=place,
        aliases=listed(aliases),
        work_modes=frozenset(WorkMode(mode) for mode in listed(modes)),
    )
    profile = world.profile()
    locations = replace(
        profile.locations, locations=(*profile.locations.locations, found)
    )
    world.change_profile(replace(profile, locations=locations))


@bdd_given(
    rx(rf'^{OWN} є вакансія "(?P<title>[^"]*)" з джерела "(?P<source>[^"]*)"{FIELDS}$')
)
def has_job(
    world: World,
    user: str | None,
    title: str,
    source: str,
    fields: str,
) -> None:
    company = dict(FIELD.findall(fields)).get("компанією")
    world.seed_job(user or world.me, title, source, fields, company)


@bdd_given(rx(r'^я ховаю вакансію "(?P<title>[^"]*)" як "(?P<reason>[^"]*)"$'))
def hide_as_not_interested(world: World, title: str, reason: str) -> None:
    world.portal.call(
        world.jobs.dismiss_jobs, world.actor(), [world.number_of(title)], reason
    )


@bdd_given(rx(r'^вакансія "(?P<title>[^"]*)" проаналізована$'))
def analysed(world: World, title: str) -> None:
    number = world.number_of(title)
    world.store.jobs.analyses[(world.actor().user_id, number)] = Analysis(
        number, JobAnalysis(score=50, summary="Підходить"), (), world.clock.now()
    )


@bdd_given(rx(r'^я подався на вакансію "(?P<title>[^"]*)"$'))
def applied(world: World, title: str) -> None:
    number = world.number_of(title)
    world.store.jobs.applications[(world.actor().user_id, number)] = Application(
        job_number=number,
        status=ApplicationStatus.APPLIED,
        applied_on=date(2026, 1, 1),
        channel=ApplicationChannel.EMAIL,
        ats=None,
        company_domains=(),
        company_emails=(),
        status_changed_at=world.clock.now(),
    )


# --- дії --------------------------------------------------------------------------------------


@bdd_given(rx(r"^я переглядаю вакансії, що вже не проходять фільтр$"))
@bdd_when(rx(r"^я переглядаю вакансії, що вже не проходять фільтр$"))
def view_filtered(world: World) -> None:
    world.view()


@bdd_when(rx(r"^я переглядаю свої джерела$"))
def view_sources(world: World) -> None:
    world.overview_now()


@bdd_when(rx(r'^я ховаю вибрані вакансії "(?P<titles>[^"]*)"$'))
def hide_chosen(world: World, titles: str) -> None:
    world.hide([world.number_of(title) for title in listed(titles)])


@bdd_when(rx(r"^я ховаю порожній вибір$"))
def hide_nothing(world: World) -> None:
    world.hide([])


@bdd_when(rx(r"^я ховаю усе, що бачив у списку$"))
def hide_seen(world: World) -> None:
    assert world.seen, "перед цим користувач нічого не бачив у списку"
    world.hide(list(world.seen))


@bdd_when(rx(r"^я ховаю вакансію з номером (?P<number>\d+)$"))
def hide_number(world: World, number: str) -> None:
    world.hide([int(number)])


# --- результат --------------------------------------------------------------------------------


def listed_item(world: World, title: str) -> FilteredJob:
    found = [item for item in world.listing if item.title == title]
    assert len(found) == 1, f"у списку «{title}»: {len(found)}"
    return found[0]


@bdd_then(rx(r"^у списку (?P<count>\d+) (?:вакансія|вакансії|вакансій)$"))
def list_count(world: World, count: str) -> None:
    assert len(world.view()) == int(count)


@bdd_then(
    rx(r'^у списку є вакансія "(?P<title>[^"]*)" з причиною "(?P<reason>[^"]*)"$')
)
def list_has(world: World, title: str, reason: str) -> None:
    world.view()
    item = listed_item(world, title)
    assert item.reason.value == reason
    assert item.number == world.job_of(title).number


@bdd_then(
    rx(
        r'^у списку є вакансія "(?P<title>[^"]*)" компанії "(?P<company>[^"]*)" з причиною "(?P<reason>[^"]*)"$'
    )
)
def list_has_company(world: World, title: str, company: str, reason: str) -> None:
    world.view()
    item = listed_item(world, title)
    assert (item.company, item.reason.value) == (company, reason)


@bdd_then(
    rx(
        r"^у списку джерел уже не проходять фільтр (?P<count>\d+) (?:вакансія|вакансії|вакансій)$"
    )
)
def overview_count(world: World, count: str) -> None:
    assert len(world.overview_now().filtered) == int(count)


@bdd_then(rx(r"^сховано (?P<count>\d+) (?:вакансію|вакансії|вакансій)$"))
def hidden_count(world: World, count: str) -> None:
    assert world.error is None, world.error
    assert world.dismissed == int(count)


@bdd_then(rx(r'^вакансія "(?P<title>[^"]*)" схована з причиною "(?P<reason>[^"]*)"$'))
def hidden_with(world: World, title: str, reason: str) -> None:
    job = world.job_of(title)
    assert job.dismissed
    assert job.dismiss_reason == reason


@bdd_then(rx(r'^вакансія "(?P<title>[^"]*)" не схована$'))
def not_hidden(world: World, title: str) -> None:
    assert not world.job_of(title).dismissed


@bdd_then(
    rx(r'^вакансія "(?P<title>[^"]*)" користувача "(?P<owner>[^"]*)" не схована$')
)
def others_not_hidden(world: World, title: str, owner: str) -> None:
    assert not world.job_of(title, owner).dismissed


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)"$'))
def got_error(world: World, code: str) -> None:
    assert world.error is not None, "помилки не було"
    assert world.error.code == code


@bdd_then(
    rx(
        r'^отримую помилку "(?P<code>[^"]*)" біля поля "(?P<field>[^"]*)" з текстом "(?P<text>[^"]*)"$'
    )
)
def got_field_error(world: World, code: str, field: str, text: str) -> None:
    error = world.error
    assert error is not None, "помилки не було"
    assert error.code == code
    assert isinstance(error, InvalidValue)
    assert (error.field, error.message) == (field, text)
