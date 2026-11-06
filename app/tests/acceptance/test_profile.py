"""Кроки для features/profile*.feature: use cases профілю + in-memory адаптери через портал.

Списки в кроках — елементи через «;»: у «Якщо» тексти (ролі, слова, синоніми) йдуть у use case
як є, з пробілами й порожніми, а значення enum-ів (рівні, формати) — обрізаними, бо вводить їх
не людина, а вибір у формі. У «Тоді» списки порівнюються обрізаними. Порожній рядок — порожній список.
"""

import inspect
from collections.abc import Callable
from datetime import datetime

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.profile import (
    ContactsData,
    LocationData,
    LocationsData,
    ProfileData,
    RulesData,
    SectionData,
    TargetData,
)
from application.profile.use_cases import ProfileUseCases
from domain.identity.ids import UserId
from domain.profile.profile import Profile
from domain.shared.errors import DomainError, InvalidFields
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.profile import InMemoryProfileUnitOfWork

scenarios(
    "features/profile.feature",
    "features/profile_target.feature",
    "features/profile_locations.feature",
    "features/profile_rules.feature",
    "features/profile_contacts.feature",
)

SECTIONS = ("target", "locations", "rules", "contacts")


class Pattern(str):
    """Регулярний вираз кроку з безіменними групами: імена беруться з параметрів функції кроку."""


def re(pattern: str) -> Pattern:
    return Pattern(pattern)


def _named(pattern: str, names: list[str]) -> str:
    """Безіменні групи `(…)` → `(?P<імʼя>…)` за порядком параметрів; `(?:…)` лишається."""
    parts = pattern.split("(")
    result = parts[0]
    free = iter(names)
    for part in parts[1:]:
        result += "(" + ("" if part.startswith("?") else f"?P<{next(free)}>") + part
    assert next(free, None) is None, f"груп менше, ніж параметрів: {pattern}"
    return result


def _step(
    register: Callable[..., Callable[..., object]],
) -> Callable[..., Callable[..., object]]:
    def decorate(target: object) -> Callable[..., object]:
        if not isinstance(target, Pattern):
            return register(target)

        def apply(func: Callable[..., object]) -> object:
            fixtures = {"world", "datatable"}
            names = [
                name
                for name in inspect.signature(func).parameters
                if name not in fixtures
            ]
            # stacklevel=2: pytest-bdd кладе крок у модуль викликача, а викликач тут — `apply`.
            return register(parsers.re(_named(str(target), names)), stacklevel=2)(func)

        return apply

    return decorate


given = _step(bdd_given)
when = _step(bdd_when)
then = _step(bdd_then)


def raw_list(text: str) -> tuple[str, ...]:
    """Як ввів користувач: без обрізання, порожній рядок — порожній список."""
    return () if text == "" else tuple(text.split(";"))


def shown_list(text: str) -> list[str]:
    return [] if text == "" else [part.strip() for part in text.split(";")]


def yes(text: str) -> bool:
    return text == "так"


def salary(text: str) -> int | None:
    return None if text == "" else int(text)


FULL = ProfileData(
    target=TargetData(
        roles=("Backend Engineer", "SRE"),
        seniority=("senior", "lead"),
        min_salary_eur=70000,
        target_domains=("fintech",),
    ),
    locations=LocationsData(
        work_modes=("remote", "hybrid"),
        locations=(
            LocationData(
                place="Valencia", aliases=("Валенсія",), work_modes=("hybrid",)
            ),
            LocationData(place="Madrid", work_modes=("remote",)),
        ),
        include_unknown_mode=False,
        relocation=True,
    ),
    rules=RulesData(
        title_keywords=("backend",), title_exclude=("junior",), stop_words=("crypto",)
    ),
    contacts=ContactsData(
        full_name="Taras",
        email="taras@example.com",
        phone="+34 600 000 000",
        linkedin_url="https://linkedin.com/in/taras",
        github_url="https://github.com/taras",
        city="Valencia",
        work_authorization="Spain / EU work authorization",
    ),
)


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.ids = ids
        self.store: dict[UserId, Profile] = {}
        self.saved_at: dict[UserId, datetime] = {}
        self.use_cases = ProfileUseCases(
            lambda: InMemoryProfileUnitOfWork(self.store, self.saved_at), clock
        )
        self.actors: dict[str, Actor] = {}
        self.current = ""
        self.before: ProfileData | None = None
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

    @property
    def actor(self) -> Actor:
        return self.actors[self.current]

    def profile(self) -> ProfileData:
        return self.portal.call(self.use_cases.get_profile, self.actor)

    def attempt(self, call: Callable[[], object]) -> None:
        """Виконує збереження; помилка домену запамʼятовується для кроків «Тоді»."""
        self.before = self.profile()
        self.error = None
        try:
            self.portal.call(call)
        except DomainError as error:
            self.error = error

    def save(self, data: SectionData) -> None:
        self.attempt(lambda: self.use_cases.save_section(self.actor, data))

    def replace(self, data: ProfileData) -> None:
        self.attempt(lambda: self.use_cases.replace_profile(self.actor, data))

    def saved(self, data: SectionData) -> None:
        """Передумова: збереження має вдатися."""
        self.save(data)
        assert self.error is None, self.error

    def problems(self) -> dict[str, str]:
        assert isinstance(self.error, InvalidFields), self.error
        return {problem.field: problem.message for problem in self.error.problems}


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


# --- хто я --------------------------------------------------------------------------------


@given(re(r'^я — користувач "([^"]*)"$'))
@when(re(r'^я стаю користувачем "([^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@given("у мене заповнений профіль")
def full_profile(world: World) -> None:
    world.replace(FULL)
    assert world.error is None


@when("я відкриваю свій профіль")
def open_profile(world: World) -> None:
    world.before = None
    world.error = None


# --- ціль ---------------------------------------------------------------------------------


def target(roles: str, levels: str, pay: str, domains: str) -> TargetData:
    return TargetData(
        roles=raw_list(roles),
        seniority=tuple(shown_list(levels)),
        min_salary_eur=salary(pay),
        target_domains=raw_list(domains),
    )


TARGET_LINE = r'ролі "([^"]*)", рівні "([^"]*)", зарплата "([^"]*)", галузі "([^"]*)"$'


@when(re(rf"^я зберігаю ціль: {TARGET_LINE}"))
def save_target(world: World, roles: str, levels: str, pay: str, domains: str) -> None:
    world.save(target(roles, levels, pay, domains))


@given(re(rf"^я зберіг ціль: {TARGET_LINE}"))
def saved_target(world: World, roles: str, levels: str, pay: str, domains: str) -> None:
    world.saved(target(roles, levels, pay, domains))


@when(re(r"^я зберігаю ціль із (\d+) галуззю$"))
def save_many_domains(world: World, count: str) -> None:
    domains = tuple(f"domain-{number}" for number in range(int(count)))
    world.save(TargetData(target_domains=domains))


@when(re(r"^я зберігаю ціль із галуззю довжиною (\d+) символ(?:ів)?$"))
def save_long_domain(world: World, length: str) -> None:
    world.save(TargetData(target_domains=("d" * int(length),)))


@when(re(r"^я зберігаю ціль із (\d+) галузями по (\d+) символів$"))
def save_full_domains(world: World, count: str, length: str) -> None:
    domains = tuple(
        f"{number:02d}".ljust(int(length), "d") for number in range(int(count))
    )
    world.save(TargetData(target_domains=domains))


@then(re(rf"^ціль: {TARGET_LINE}"))
def check_target(world: World, roles: str, levels: str, pay: str, domains: str) -> None:
    saved = world.profile().target
    assert list(saved.roles) == shown_list(roles)
    assert list(saved.seniority) == shown_list(levels)
    assert saved.min_salary_eur == salary(pay)
    assert list(saved.target_domains) == shown_list(domains)


@then(re(r"^у цілі (\d+) галузей$"))
def count_domains(world: World, count: str) -> None:
    assert len(world.profile().target.target_domains) == int(count)


@then("ціль порожня")
def target_empty(world: World) -> None:
    assert world.profile().target == TargetData()


# --- локації ------------------------------------------------------------------------------

LOCATIONS_LINE = r'із загальними форматами "([^"]*)", невідомий формат "([^"]*)", релокація "([^"]*)"'


def locations(
    modes: str, unknown: str, relocation: str, table: list[list[str]] | None
) -> LocationsData:
    rows = (table or [])[1:]  # перший рядок — заголовок
    return LocationsData(
        work_modes=tuple(shown_list(modes)),
        locations=tuple(
            LocationData(
                place=place,
                aliases=raw_list(aliases),
                work_modes=tuple(shown_list(formats)),
            )
            for place, aliases, formats in rows
        ),
        include_unknown_mode=yes(unknown),
        relocation=yes(relocation),
    )


@when(re(rf"^я зберігаю локації {LOCATIONS_LINE}:$"))
def save_locations(
    world: World,
    datatable: list[list[str]],
    modes: str,
    unknown: str,
    relocation: str,
) -> None:
    world.save(locations(modes, unknown, relocation, datatable))


@given(re(rf"^я зберіг локації {LOCATIONS_LINE}:$"))
def saved_locations(
    world: World,
    datatable: list[list[str]],
    modes: str,
    unknown: str,
    relocation: str,
) -> None:
    world.saved(locations(modes, unknown, relocation, datatable))


@when("я зберігаю порожній розділ локацій")
def save_no_locations(world: World) -> None:
    world.save(LocationsData())


@when(re(r"^я зберігаю локацію з місцем довжиною (\d+) символ(?:ів)?$"))
def save_long_place(world: World, length: str) -> None:
    place = "p" * int(length)
    world.save(
        LocationsData(locations=(LocationData(place=place, work_modes=("remote",)),))
    )


@when(re(r'^я зберігаю локацію "([^"]*)" із (\d+) синонімом$'))
def save_many_aliases(world: World, place: str, count: str) -> None:
    aliases = tuple(f"alias-{number}" for number in range(int(count)))
    world.save(
        LocationsData(
            locations=(
                LocationData(place=place, aliases=aliases, work_modes=("remote",)),
            )
        )
    )


@when(re(r'^я зберігаю локацію "([^"]*)" із (\d+) синонімами по (\d+) символів$'))
def save_full_aliases(world: World, place: str, count: str, length: str) -> None:
    aliases = tuple(
        f"{number:02d}".ljust(int(length), "a") for number in range(int(count))
    )
    world.save(
        LocationsData(
            locations=(
                LocationData(place=place, aliases=aliases, work_modes=("remote",)),
            )
        )
    )


@when(re(r"^я зберігаю (\d+) локаці(?:ю|й)$"))
def save_n_locations(world: World, count: str) -> None:
    rows = tuple(
        LocationData(place=f"Place {number}", work_modes=("remote",))
        for number in range(int(count))
    )
    world.save(LocationsData(locations=rows))


@then(re(r'^локації за порядком: "([^"]*)"$'))
def check_order(world: World, places: str) -> None:
    saved = world.profile().locations.locations
    assert [location.place for location in saved] == shown_list(places)


@then(re(r'^у локації "([^"]*)" синоніми "([^"]*)" і формати "([^"]*)"$'))
def check_location(world: World, place: str, aliases: str, formats: str) -> None:
    saved = {item.place: item for item in world.profile().locations.locations}
    assert list(saved[place].aliases) == shown_list(aliases)
    assert list(saved[place].work_modes) == shown_list(formats)


@then(re(r'^у локації "([^"]*)" (\d+) синонімів$'))
def count_aliases(world: World, place: str, count: str) -> None:
    saved = {item.place: item for item in world.profile().locations.locations}
    assert len(saved[place].aliases) == int(count)


@then(re(r"^збережено (\d+) локацій$"))
def count_locations(world: World, count: str) -> None:
    assert len(world.profile().locations.locations) == int(count)


@then(re(r'^загальні формати "([^"]*)"$'))
def check_global_modes(world: World, modes: str) -> None:
    assert list(world.profile().locations.work_modes) == shown_list(modes)


@then("локації порожні")
def locations_empty(world: World) -> None:
    saved = world.profile().locations
    assert (saved.work_modes, saved.locations) == ((), ())


@then("невідомий формат вакансії за замовчуванням приймається")
def unknown_mode_default(world: World) -> None:
    assert world.profile().locations.include_unknown_mode is True


@then("невідомий формат вакансії не приймається")
def unknown_mode_off(world: World) -> None:
    assert world.profile().locations.include_unknown_mode is False


@then("релокацію за замовчуванням не розглядаю")
def relocation_default(world: World) -> None:
    assert world.profile().locations.relocation is False


@then("релокацію розглядаю")
def relocation_on(world: World) -> None:
    assert world.profile().locations.relocation is True


# --- правила ------------------------------------------------------------------------------

RULES_LINE = r'у назві "([^"]*)", виключення "([^"]*)", стоп-слова "([^"]*)"$'


def rules(keywords: str, exclude: str, stops: str) -> RulesData:
    return RulesData(
        title_keywords=raw_list(keywords),
        title_exclude=raw_list(exclude),
        stop_words=raw_list(stops),
    )


@when(re(rf"^я зберігаю правила: {RULES_LINE}"))
def save_rules(world: World, keywords: str, exclude: str, stops: str) -> None:
    world.save(rules(keywords, exclude, stops))


@given(re(rf"^я зберіг правила: {RULES_LINE}"))
def saved_rules(world: World, keywords: str, exclude: str, stops: str) -> None:
    world.saved(rules(keywords, exclude, stops))


@when(re(r"^я зберігаю правила з (\d+) словами в кожному списку$"))
def save_many_words(world: World, count: str) -> None:
    words = tuple(f"word-{number}" for number in range(int(count)))
    world.save(RulesData(title_keywords=words, title_exclude=words, stop_words=words))


@then(re(rf"^правила: {RULES_LINE}"))
def check_rules(world: World, keywords: str, exclude: str, stops: str) -> None:
    saved = world.profile().rules
    assert list(saved.title_keywords) == shown_list(keywords)
    assert list(saved.title_exclude) == shown_list(exclude)
    assert list(saved.stop_words) == shown_list(stops)


@then("назва вакансії не обмежена")
def title_unrestricted(world: World) -> None:
    assert world.profile().rules.title_keywords == ()


@then(re(r"^у кожному списку правил (\d+) слів$"))
def count_words(world: World, count: str) -> None:
    saved = world.profile().rules
    assert [
        len(saved.title_keywords),
        len(saved.title_exclude),
        len(saved.stop_words),
    ] == [int(count)] * 3


# --- контакти -----------------------------------------------------------------------------

CONTACTS_LINE = (
    r'ім’я "([^"]*)", email "([^"]*)", телефон "([^"]*)", LinkedIn "([^"]*)", '
    r'GitHub "([^"]*)", місто "([^"]*)", дозвіл "([^"]*)"$'
)
CONTACTS_THEN = (
    r'email "([^"]*)", ім’я "([^"]*)", телефон "([^"]*)", LinkedIn "([^"]*)", '
    r'GitHub "([^"]*)", місто "([^"]*)", дозвіл "([^"]*)"$'
)


def contacts(
    name: str, email: str, phone: str, linkedin: str, github: str, city: str, auth: str
) -> ContactsData:
    return ContactsData(
        full_name=name,
        email=email,
        phone=phone,
        linkedin_url=linkedin,
        github_url=github,
        city=city,
        work_authorization=auth,
    )


@when(re(rf"^я зберігаю контакти: {CONTACTS_LINE}"))
def save_contacts(
    world: World,
    name: str,
    email: str,
    phone: str,
    linkedin: str,
    github: str,
    city: str,
    auth: str,
) -> None:
    world.save(contacts(name, email, phone, linkedin, github, city, auth))


@given(re(rf"^я зберіг контакти: {CONTACTS_LINE}"))
def saved_contacts(
    world: World,
    name: str,
    email: str,
    phone: str,
    linkedin: str,
    github: str,
    city: str,
    auth: str,
) -> None:
    world.saved(contacts(name, email, phone, linkedin, github, city, auth))


@when(re(r'^я зберігаю контакти з email "([^"]*)"$'))
def save_contacts_email(world: World, email: str) -> None:
    world.save(ContactsData(email=email))


@when(re(r'^я зберігаю контакти з LinkedIn "([^"]*)"$'))
def save_contacts_linkedin(world: World, url: str) -> None:
    world.save(ContactsData(linkedin_url=url))


@when(re(r'^я зберігаю контакти з GitHub "([^"]*)"$'))
def save_contacts_github(world: World, url: str) -> None:
    world.save(ContactsData(github_url=url))


@when(re(r'^я зберігаю контакти з полем "([^"]*)" довжиною (\d+) символ(?:ів)?$'))
def save_contacts_long(world: World, field: str, length: str) -> None:
    world.save(ContactsData(**{field: "x" * int(length)}))


@then(re(rf"^контакти: {CONTACTS_THEN}"))
def check_contacts(
    world: World,
    email: str,
    name: str,
    phone: str,
    linkedin: str,
    github: str,
    city: str,
    auth: str,
) -> None:
    assert world.profile().contacts == contacts(
        name, email, phone, linkedin, github, city, auth
    )


@then("контакти порожні")
def contacts_empty(world: World) -> None:
    assert world.profile().contacts == ContactsData()


@then(re(r"^ім’я в контактах має (\d+) символів$"))
def name_length(world: World, length: str) -> None:
    assert len(world.profile().contacts.full_name) == int(length)


# --- профіль цілком -----------------------------------------------------------------------


@then("профіль порожній: без ролей, локацій, правил і контактів")
def profile_empty(world: World) -> None:
    saved = world.profile()
    assert saved == ProfileData()


@when("я замінюю профіль порожнім")
def replace_with_empty(world: World) -> None:
    world.replace(ProfileData())


@when(
    re(
        r'^я замінюю профіль: ціль із ролями "([^"]*)", правила зі стоп-словами "([^"]*)", '
        r'контакти з email "([^"]*)"$'
    )
)
def replace_with_parts(world: World, roles: str, stops: str, email: str) -> None:
    world.replace(
        ProfileData(
            target=TargetData(roles=raw_list(roles)),
            rules=RulesData(stop_words=raw_list(stops)),
            contacts=ContactsData(email=email),
        )
    )


@when(
    re(
        r'^я замінюю профіль: ціль із зарплатою "([^"]*)", локацію "([^"]*)" без формату, '
        r'контакти з email "([^"]*)"$'
    )
)
def replace_with_errors(world: World, pay: str, place: str, email: str) -> None:
    world.replace(
        ProfileData(
            target=TargetData(min_salary_eur=salary(pay)),
            locations=LocationsData(locations=(LocationData(place=place),)),
            contacts=ContactsData(email=email),
        )
    )


@then("у сховищі профілів нічого немає")
def nothing_stored(world: World) -> None:
    assert world.store == {}


@then(re(r"^у сховищі профілів — (\d+) користувачі$"))
def stored_users(world: World, count: str) -> None:
    assert len(world.store) == int(count)


@then("мій профіль не змінився")
def unchanged(world: World) -> None:
    assert world.before is not None
    assert world.profile() == world.before


@then(re(r'^інші розділи профілю, крім "([^"]*)", не змінились$'))
def other_sections_unchanged(world: World, section: str) -> None:
    assert world.error is None, world.error
    assert world.before is not None
    after = world.profile()
    for name in SECTIONS:
        if name != section:
            assert getattr(after, name) == getattr(world.before, name), name
    assert getattr(after, section) != getattr(world.before, section)


# --- помилки ------------------------------------------------------------------------------


@then(re(r'^отримую помилку "([^"]*)"$'))
def expect_error(world: World, code: str) -> None:
    assert world.error is not None
    assert world.error.code == code


@then(re(r'^помилка поля "([^"]*)"$'))
def expect_field(world: World, field: str) -> None:
    assert field in world.problems()


@then(re(r'^помилка поля "([^"]*)" з текстом "([^"]*)"$'))
def expect_field_text(world: World, field: str, text: str) -> None:
    assert world.problems().get(field) == text


@then(re(r"^кількість помилок полів — (\d+)$"))
def expect_problem_count(world: World, count: str) -> None:
    assert len(world.problems()) == int(count)
