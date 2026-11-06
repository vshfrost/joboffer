"""Кроки для features/sources_import.feature: імпорт вакансій із джерела (фільтр профілю, дедуп, дописування
тексту) через use cases й in-memory адаптери, без мережі й бази.

Вакансії джерела накопичуються кроками «джерело віддає вакансію …» і йдуть в імпорт одним викликом
(«я імпортую вакансії з Greenhouse компанії …»). Поля вакансії — необовʼязкові пари `<назва поля> "<значення>"` у
будь-якому порядку: компанією, з текстом, посиланням, локацією, форматом. Без них текст і посилання унікальні
(`Опис вакансії №N`, `https://jobs.example/N`, N — наскрізний номер вакансії джерела в сценарії). Профіль
користувача збирається кроками «у моєму профілі …».
"""

import functools
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.jobs import JobData, JobInput, JobSearchInput
from application.jobs.use_cases import JobUseCases
from application.sources.imports import SourceImportUseCases
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.jobs.linkedin import linkedin_job_url
from domain.profile.locations import SearchLocation
from domain.profile.modes import WorkMode
from domain.profile.profile import Profile
from domain.shared.errors import DomainError, NotFound
from domain.sources.importing import ImportSummary
from domain.sources.kinds import FeedSource, Platform, SourceKind
from domain.sources.posting import Posting
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store
from tests.support.sources import InMemorySourceImportUnitOfWork

scenarios("features/sources_import.feature")

Step = Callable[..., Any]
PLATFORMS = {
    "Greenhouse": Platform.GREENHOUSE,
    "Ashby": Platform.ASHBY,
    "Lever": Platform.LEVER,
}
FEEDS = {"DOU": FeedSource.DOU, "Djinni": FeedSource.DJINNI}
FIELDS = (
    r'(?P<fields>(?:,? (?:компанією|з текстом|посиланням|локацією|форматом) "[^"]*")*)'
)
FIELD = re.compile(r'(компанією|з текстом|посиланням|локацією|форматом) "([^"]*)"')


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
    """Один текст — і «Припустимо …», і «Якщо …»."""

    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(succeeded(step))
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


def listed(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split(";") if part.strip())


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.store = Store.empty()
        self.profiles: dict[UserId, Profile] = {}
        self.imports = SourceImportUseCases(
            lambda: InMemorySourceImportUnitOfWork(self.store, self.profiles),
            clock,
            ids,
        )
        self.jobs = JobUseCases(lambda: InMemoryJobUnitOfWork(self.store), clock, ids)
        self.actors: dict[str, Actor] = {}
        self.current = ""
        self.posted = 0
        self.batch: list[Posting] = []
        self.last_batch: list[Posting] = []
        self.summary: ImportSummary | None = None
        self.error: DomainError | None = None

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
        self.summary = None
        self.error = None

    @property
    def actor(self) -> Actor:
        return self.actors[self.current]

    @property
    def profile(self) -> Profile:
        return self.profiles.get(self.actor.user_id, Profile())

    def change_profile(self, profile: Profile) -> None:
        self.profiles[self.actor.user_id] = profile

    def offer(self, title: str, fields: str) -> None:
        values = dict(FIELD.findall(fields))
        self.posted += 1
        mode = values.get("форматом", "")
        location = values.get("локацією", "")
        self.batch.append(
            Posting(
                title=title,
                url=values.get("посиланням", f"https://jobs.example/{self.posted}"),
                text=values.get("з текстом", f"Опис вакансії №{self.posted}"),
                company=values.get("компанією") or None,
                locations=(location,) if location else (),
                work_mode=WorkMode(mode) if mode else None,
            )
        )

    def run_import(self, source: SourceKind, company: str) -> None:
        postings, self.batch = self.batch, []
        self.last_batch = postings
        self.error = None
        try:
            self.summary = self.portal.call(
                self.imports.import_postings,
                self.actor.user_id,
                source,
                postings,
                company,
            )
        except DomainError as error:
            self.error = error

    def my_jobs(self) -> list[Any]:
        return self.portal.call(
            self.jobs.list_jobs, self.actor, JobSearchInput(limit=200)
        )

    def job(self, number: int) -> JobData:
        try:
            return self.portal.call(self.jobs.get_job, self.actor, number)
        except NotFound as error:
            raise AssertionError(f"вакансії {number} у користувача нема") from error

    def seed_alert(self, title: str, company: str, linkedin_id: str) -> None:
        """Вакансія з листа-алерту LinkedIn без тексту: її створює синк пошти, тут — передумова."""

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


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


# --- хто я, час -----------------------------------------------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_given(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@bdd_given(rx(r"^минає (?P<days>\d+) (?:доба|діб)$"))
def days_pass(world: World, days: str) -> None:
    world.clock.advance(timedelta(days=int(days)))


# --- профіль --------------------------------------------------------------------------------


@bdd_given(rx(r'^у моєму профілі слова назви "(?P<words>[^"]*)"$'))
def profile_keywords(world: World, words: str) -> None:
    rules = replace(world.profile.rules, title_keywords=listed(words))
    world.change_profile(replace(world.profile, rules=rules))


@bdd_given(rx(r'^у моєму профілі виключені слова назви "(?P<words>[^"]*)"$'))
def profile_exclude(world: World, words: str) -> None:
    rules = replace(world.profile.rules, title_exclude=listed(words))
    world.change_profile(replace(world.profile, rules=rules))


@bdd_given(rx(r'^у моєму профілі формати "(?P<modes>[^"]*)"$'))
def profile_modes(world: World, modes: str) -> None:
    locations = replace(
        world.profile.locations,
        work_modes=frozenset(WorkMode(mode) for mode in listed(modes)),
    )
    world.change_profile(replace(world.profile, locations=locations))


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
    locations = replace(
        world.profile.locations,
        locations=(*world.profile.locations.locations, found),
    )
    world.change_profile(replace(world.profile, locations=locations))


@bdd_given(rx(r"^у моєму профілі невідомий формат не береться$"))
def profile_unknown_mode(world: World) -> None:
    locations = replace(world.profile.locations, include_unknown_mode=False)
    world.change_profile(replace(world.profile, locations=locations))


# --- вакансії користувача й джерела ---------------------------------------------------------


@bdd_given(
    rx(
        r'^є вакансія "(?P<title>[^"]*)" компанії "(?P<company>[^"]*)"'
        r'(?P<fields>(?: з (?:посиланням|текстом) "[^"]*")*)$'
    )
)
def existing_job(world: World, title: str, company: str, fields: str) -> None:
    values = dict(re.findall(r'з (посиланням|текстом) "([^"]*)"', fields))
    added = world.portal.call(
        world.jobs.add_job,
        world.actor,
        JobInput(
            text=values.get("текстом", f"Ручний опис вакансії «{title}»"),
            url=values.get("посиланням", ""),
            title=title,
            company=company,
        ),
    )
    assert added.job_number >= 1


@bdd_given(
    rx(
        r'^є вакансія з листа-алерту "(?P<title>[^"]*)" компанії "(?P<company>[^"]*)"'
        r" з посиланням LinkedIn (?P<linkedin_id>\d+)$"
    )
)
def alert_job(world: World, title: str, company: str, linkedin_id: str) -> None:
    world.seed_alert(title, company, linkedin_id)


@bdd_given(rx(r"^я сховав вакансію (?P<number>\d+)$"))
def dismiss_job(world: World, number: str) -> None:
    world.portal.call(world.jobs.dismiss_jobs, world.actor, [int(number)], "не цікаво")


@bdd_given(rx(rf'^джерело віддає вакансію "(?P<title>[^"]*)"{FIELDS}$'))
def source_offers(world: World, title: str, fields: str) -> None:
    world.offer(title, fields)


@bdd_given(rx(r"^ті самі вакансії приходять ще раз$"))
@bdd_when(rx(r"^ті самі вакансії приходять ще раз$"))
def source_offers_again(world: World) -> None:
    world.batch = list(world.last_batch)


# --- імпорт ---------------------------------------------------------------------------------


@action(
    r'^я імпортую вакансії з (?P<platform>Greenhouse|Ashby|Lever) компанії "(?P<company>[^"]*)"$'
)
def import_ats(world: World, platform: str, company: str) -> None:
    world.run_import(PLATFORMS[platform], company)


@action(r"^я імпортую вакансії зі стрічки (?P<feed>DOU|Djinni)$")
def import_feed(world: World, feed: str) -> None:
    world.run_import(FEEDS[feed], "")


# --- результат ------------------------------------------------------------------------------


@bdd_then(
    rx(
        r"^підсумок: знайдено (?P<found>\d+), імпортовано (?P<imported>\d+), відкинуто (?P<filtered>\d+),"
        r" дублів (?P<duplicate>\d+), доповнено (?P<completed>\d+)$"
    )
)
def summary_is(
    world: World,
    found: str,
    imported: str,
    filtered: str,
    duplicate: str,
    completed: str,
) -> None:
    assert world.error is None, world.error
    assert world.summary == ImportSummary(
        found=int(found),
        imported=int(imported),
        filtered=int(filtered),
        duplicate=int(duplicate),
        completed=int(completed),
    )


@bdd_then(rx(r"^у мене (?P<count>\d+) вакансі(?:я|ї|й)$"))
def job_count(world: World, count: str) -> None:
    assert len(world.my_jobs()) == int(count)


@bdd_then(
    rx(
        r'^вакансія (?P<number>\d+) має назву "(?P<title>[^"]*)", компанію "(?P<company>[^"]*)"'
        r' і посилання "(?P<url>[^"]*)"$'
    )
)
def job_identity(world: World, number: str, title: str, company: str, url: str) -> None:
    job = world.job(int(number))
    assert (job.title, job.company, job.url) == (title, company, url)


@bdd_then(rx(r'^вакансія (?P<number>\d+) має джерело "(?P<source>[^"]*)"$'))
def job_source(world: World, number: str, source: str) -> None:
    assert world.job(int(number)).source == source


@bdd_then(rx(r'^вакансія (?P<number>\d+) має локацію "(?P<location>[^"]*)"$'))
def job_location(world: World, number: str, location: str) -> None:
    assert world.job(int(number)).location == location


@bdd_then(rx(r'^вакансія (?P<number>\d+) має текст "(?P<text>[^"]*)"$'))
def job_text(world: World, number: str, text: str) -> None:
    assert world.job(int(number)).text == text


@bdd_then(rx(r"^вакансія (?P<number>\d+) потребує тексту$"))
def job_needs_text(world: World, number: str) -> None:
    assert world.job(int(number)).needs_text is True


@bdd_then(rx(r"^вакансія (?P<number>\d+) не потребує тексту$"))
def job_has_text(world: World, number: str) -> None:
    assert world.job(int(number)).needs_text is False
