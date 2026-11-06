"""Кроки для features/onboarding_*.feature: use cases онбордингу + in-memory адаптери через портал.

Дані користувача кладуться напряму в сховища контекстів (профіль — через справжні use cases профілю),
а онбординг читає їх через свій unit of work — як це робить Postgres-адаптер.
"""

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
from application.contracts.onboarding import OnboardingData
from application.contracts.profile import (
    ContactsData,
    LocationData,
    LocationsData,
    TargetData,
)
from application.onboarding.use_cases import OnboardingUseCases
from application.profile.use_cases import ProfileUseCases
from domain.facts.fact import OriginalCv
from domain.identity.ids import GrantId, UserId
from domain.identity.session import TokenDigest
from domain.mail.mail import MailInbox
from domain.oauth.entities import Grant, StoredToken, TokenKind
from domain.oauth.ids import ClientId
from domain.oauth.rules import REFRESH_TTL
from domain.photos.ids import PhotoId
from domain.photos.photo import NewPhoto
from domain.shared.errors import DomainError
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.onboarding import InMemoryOnboardingUnitOfWork, OnboardingWorld
from tests.support.photos import InMemoryPhotos
from tests.support.profile import InMemoryProfileUnitOfWork

scenarios(
    "features/onboarding_steps.feature",
    "features/onboarding_tips.feature",
    "features/onboarding_users.feature",
)


def rx(pattern: str) -> Any:
    return parsers.re(pattern)


def setup(pattern: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
    """Крок, що читається і після «Припустимо», і після «Якщо» (через «І»)."""

    def decorate(step: Callable[..., None]) -> Callable[..., None]:
        bdd_given(rx(pattern), stacklevel=2)(step)
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


def listed(text: str) -> list[str]:
    return [] if text.strip() == "" else [part.strip() for part in text.split(";")]


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.data = OnboardingWorld()
        self.onboarding = OnboardingUseCases(
            lambda: InMemoryOnboardingUnitOfWork(self.data), clock
        )
        self.profile = ProfileUseCases(
            lambda: InMemoryProfileUnitOfWork(
                self.data.profiles, self.data.profiles_saved_at
            ),
            clock,
        )
        self.actors: dict[str, Actor] = {}
        self.current = ""
        self.shown: OnboardingData | None = None
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

    def attempt(self, call: Callable[[], Any]) -> None:
        self.error = None
        try:
            self.portal.call(call)
        except DomainError as error:
            self.error = error

    def open(self) -> OnboardingData:
        self.error = None
        self.shown = self.portal.call(self.onboarding.get_onboarding, self.actor)
        return self.shown

    def connect_claude(self, *, refresh_used: bool) -> None:
        grant = Grant(
            id=GrantId(self.ids.new()),
            user_id=self.actor.user_id,
            client_id=ClientId(self.ids.new()),
            resource="https://example.test/mcp",
            created_at=self.clock.now(),
        )
        self.data.oauth.grants[grant.id] = grant
        for kind in (TokenKind.ACCESS, TokenKind.REFRESH):
            digest = TokenDigest.from_token(f"{kind}-{grant.id}")
            self.data.oauth.tokens[digest] = StoredToken(
                digest=digest,
                kind=kind,
                grant_id=grant.id,
                expires_at=self.clock.now() + REFRESH_TTL,
                consumed_at=(
                    self.clock.now()
                    if refresh_used and kind is TokenKind.REFRESH
                    else None
                ),
            )

    def revoke_claude(self) -> None:
        for grant_id, grant in list(self.data.oauth.grants.items()):
            if grant.user_id == self.actor.user_id:
                self.data.oauth.grants[grant_id] = grant.revoke(self.clock.now())


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def shown(world: World) -> OnboardingData:
    assert world.shown is not None, "онбординг не відкрито"
    return world.shown


# --- хто я --------------------------------------------------------------------------------


@setup(r'^я — користувач "(?P<name>[^"]*)"$')
@setup(r'^я стаю користувачем "(?P<name>[^"]*)"$')
def become_user(world: World, name: str) -> None:
    world.become(name)


# --- дані, за якими рахуються кроки -----------------------------------------------------------


@setup(r'^я задав ролі цілі "(?P<roles>[^"]*)"$')
def set_roles(world: World, roles: str) -> None:
    world.portal.call(
        world.profile.save_section, world.actor, TargetData(roles=tuple(listed(roles)))
    )


@setup(r"^я задав мінімальну зарплату (?P<pay>\d+) без ролей$")
def set_pay(world: World, pay: str) -> None:
    world.portal.call(
        world.profile.save_section,
        world.actor,
        TargetData(roles=(), min_salary_eur=int(pay)),
    )


@setup(r'^я додав локацію "(?P<place>[^"]*)"$')
def add_location(world: World, place: str) -> None:
    section = LocationsData(
        locations=(LocationData(place=place, work_modes=("remote",)),)
    )
    world.portal.call(world.profile.save_section, world.actor, section)


@setup(r'^я задав формат роботи "(?P<mode>[^"]*)" без локацій$')
def set_work_mode(world: World, mode: str) -> None:
    section = LocationsData(work_modes=(mode,), locations=())
    world.portal.call(world.profile.save_section, world.actor, section)


@setup(r'^я задав імʼя "(?P<name>[^"]*)" та email "(?P<email>[^"]*)"$')
def set_contacts(world: World, name: str, email: str) -> None:
    section = ContactsData(full_name=name, email=email)
    world.portal.call(world.profile.save_section, world.actor, section)


@setup(r"^Claude підключено: грант діє, refresh-токен чинний$")
def claude_connected(world: World) -> None:
    world.connect_claude(refresh_used=False)


@setup(r"^Claude підключено: грант діє, refresh-токен використано$")
def claude_refresh_used(world: World) -> None:
    world.connect_claude(refresh_used=True)


@setup(r"^я відкликав грант Claude$")
def revoke_claude(world: World) -> None:
    world.revoke_claude()


@setup(r"^минуло (?P<days>\d+) (?:день|дні|днів)$")
def days_passed(world: World, days: str) -> None:
    world.clock.advance(timedelta(days=int(days)))


@setup(r"^я зберіг оригінал CV$")
def save_original_cv(world: World) -> None:
    world.data.facts.cvs[world.actor.user_id] = OriginalCv(
        "Alice Example\nPython developer", "cv.pdf", world.clock.now()
    )


@setup(r"^я додав фото$")
def add_photo(world: World) -> None:
    photo = NewPhoto(data=b"jpeg", width=858, height=960)
    world.portal.call(
        InMemoryPhotos(world.data.photos).add,
        world.actor.user_id,
        PhotoId(world.ids.new()),
        photo,
        world.clock.now(),
    )


@setup(r"^я видалив фото (?P<number>\d+)$")
def delete_photo(world: World, number: str) -> None:
    world.portal.call(
        InMemoryPhotos(world.data.photos).delete, world.actor.user_id, int(number)
    )


@setup(r"^у мене є особиста адреса пошти$")
def mail_address(world: World) -> None:
    world.data.mail.inboxes[world.actor.user_id] = MailInbox(
        "a" * 12, world.clock.now()
    )


@setup(r"^у мене зроблено всі обов'язкові кроки$")
def required_steps_done(world: World) -> None:
    set_roles(world, "Backend Developer")
    add_location(world, "Valencia")
    set_contacts(world, "Alice Example", "alice@example.com")
    claude_connected(world)
    save_original_cv(world)


# --- підказки ---------------------------------------------------------------------------------


@setup(r'^я (?:позначаю|позначив) підказку "(?P<key>[^"]*)" баченою$')
def mark_seen(world: World, key: str) -> None:
    world.attempt(lambda: world.onboarding.mark_tip_seen(world.actor, key))


@setup(r'^я (?:ховаю|сховав) підказку "(?P<key>[^"]*)"$')
def dismiss(world: World, key: str) -> None:
    world.attempt(lambda: world.onboarding.dismiss_tip(world.actor, key))


# --- перегляд ---------------------------------------------------------------------------------


@setup(r"^я відкриваю онбординг$")
def open_onboarding(world: World) -> None:
    world.open()


@bdd_then(rx(r'^кроки за порядком: "(?P<keys>[^"]*)"$'))
def step_order(world: World, keys: str) -> None:
    assert [step.key for step in shown(world).steps] == listed(keys)


@bdd_then(rx(r'^зроблені кроки: "(?P<keys>[^"]*)"$'))
def done_steps(world: World, keys: str) -> None:
    assert [step.key for step in shown(world).steps if step.done] == listed(keys)


@bdd_then(rx(r'^необов\'язкові кроки: "(?P<keys>[^"]*)"$'))
def optional_steps(world: World, keys: str) -> None:
    assert [step.key for step in shown(world).steps if step.optional] == listed(keys)


@bdd_then("онбординг завершено")
def is_complete(world: World) -> None:
    assert shown(world).complete is True


@bdd_then("онбординг не завершено")
def is_not_complete(world: World) -> None:
    assert shown(world).complete is False


@bdd_then(rx(r'^підказки за порядком: "(?P<keys>[^"]*)"$'))
def tip_order(world: World, keys: str) -> None:
    assert [tip.key for tip in shown(world).tips] == listed(keys)


@bdd_then(rx(r'^бачені підказки: "(?P<keys>[^"]*)"$'))
def seen_tips(world: World, keys: str) -> None:
    assert [tip.key for tip in shown(world).tips if tip.seen] == listed(keys)


@bdd_then(rx(r'^сховані підказки: "(?P<keys>[^"]*)"$'))
def dismissed_tips(world: World, keys: str) -> None:
    assert [tip.key for tip in shown(world).tips if tip.dismissed] == listed(keys)


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def error_message(world: World, code: str, message: str) -> None:
    assert world.error is not None, "помилки не було"
    assert (world.error.code, world.error.message) == (code, message)
