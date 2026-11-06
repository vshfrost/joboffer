"""Use cases профілю: порожній профіль, збереження розділу, повна заміна, ізоляція користувачів."""

from datetime import datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal

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
from domain.shared.errors import FieldProblem, InvalidFields
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.profile import InMemoryProfileUnitOfWork

TARGET = TargetData(
    roles=("Backend Engineer",),
    seniority=("senior",),
    min_salary_eur=70000,
    target_domains=("fintech",),
)
LOCATIONS = LocationsData(
    work_modes=("remote", "hybrid"),
    locations=(
        LocationData(place="Valencia", aliases=("Валенсія",), work_modes=("hybrid",)),
        LocationData(place="Madrid", work_modes=("remote", "hybrid", "onsite")),
    ),
    include_unknown_mode=False,
    relocation=True,
)
RULES = RulesData(
    title_keywords=("backend",), title_exclude=("junior",), stop_words=("crypto",)
)
CONTACTS = ContactsData(full_name="Taras", email="taras@example.com", city="Valencia")
FULL = ProfileData(target=TARGET, locations=LOCATIONS, rules=RULES, contacts=CONTACTS)


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.store: dict[UserId, Profile] = {}
        self.saved_at: dict[UserId, datetime] = {}
        self.alice = self._actor(ids)
        self.bob = self._actor(ids)
        self.use_cases = ProfileUseCases(
            lambda: InMemoryProfileUnitOfWork(self.store, self.saved_at), clock
        )

    @staticmethod
    def _actor(ids: SequentialIds) -> Actor:
        return Actor(
            user_id=UserId(ids.new()),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )

    def get(self, actor: Actor) -> ProfileData:
        return self.portal.call(self.use_cases.get_profile, actor)

    def save(self, actor: Actor, data: SectionData) -> ProfileData:
        return self.portal.call(self.use_cases.save_section, actor, data)

    def replace(self, actor: Actor, data: ProfileData) -> ProfileData:
        return self.portal.call(self.use_cases.replace_profile, actor, data)


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def test_a_new_user_has_an_empty_profile_and_no_stored_row(world: World) -> None:
    profile = world.get(world.alice)
    assert profile == ProfileData()
    assert profile.locations.include_unknown_mode is True
    assert world.store == {}


def test_save_target_changes_only_the_target(world: World) -> None:
    world.replace(world.alice, FULL)
    updated = world.save(world.alice, TargetData(roles=("SRE",)))
    assert updated == ProfileData(
        target=TargetData(roles=("SRE",)),
        locations=LOCATIONS,
        rules=RULES,
        contacts=CONTACTS,
    )
    assert world.get(world.alice) == updated


def test_save_locations_changes_only_the_locations(world: World) -> None:
    world.replace(world.alice, FULL)
    updated = world.save(world.alice, LocationsData(relocation=False))
    assert updated == ProfileData(
        target=TARGET,
        locations=LocationsData(relocation=False),
        rules=RULES,
        contacts=CONTACTS,
    )


def test_save_rules_changes_only_the_rules(world: World) -> None:
    world.replace(world.alice, FULL)
    updated = world.save(world.alice, RulesData(stop_words=("gambling",)))
    assert updated == ProfileData(
        target=TARGET,
        locations=LOCATIONS,
        rules=RulesData(stop_words=("gambling",)),
        contacts=CONTACTS,
    )


def test_save_contacts_changes_only_the_contacts(world: World) -> None:
    world.replace(world.alice, FULL)
    updated = world.save(world.alice, ContactsData(city="Madrid"))
    assert updated == ProfileData(
        target=TARGET,
        locations=LOCATIONS,
        rules=RULES,
        contacts=ContactsData(city="Madrid"),
    )


def test_saving_one_section_of_an_empty_profile_leaves_the_others_empty(
    world: World,
) -> None:
    updated = world.save(world.alice, RulesData(title_exclude=("intern",)))
    assert updated == ProfileData(rules=RulesData(title_exclude=("intern",)))


def test_saved_values_are_normalized(world: World) -> None:
    updated = world.save(
        world.alice,
        TargetData(roles=("  SRE ", "sre", ""), seniority=("lead",)),
    )
    assert updated.target == TargetData(roles=("SRE",), seniority=("lead",))


def test_seniority_and_work_modes_come_back_in_a_fixed_order(world: World) -> None:
    saved = world.save(
        world.alice,
        LocationsData(work_modes=("onsite", "remote", "hybrid")),
    )
    assert saved.locations.work_modes == ("remote", "hybrid", "onsite")
    saved = world.save(
        world.alice, TargetData(seniority=("principal", "junior", "lead"))
    )
    assert saved.target.seniority == ("junior", "lead", "principal")


def test_location_order_is_kept(world: World) -> None:
    world.save(world.alice, LOCATIONS)
    assert [place.place for place in world.get(world.alice).locations.locations] == [
        "Valencia",
        "Madrid",
    ]


def test_invalid_data_changes_nothing_and_names_the_fields(world: World) -> None:
    world.replace(world.alice, FULL)
    with pytest.raises(InvalidFields) as raised:
        world.save(
            world.alice,
            LocationsData(
                locations=(
                    LocationData(place="Valencia", work_modes=("hybrid",)),
                    LocationData(place="valencia", work_modes=()),
                )
            ),
        )
    assert raised.value.problems == (
        FieldProblem(
            "locations.1.place", "Місця в локаціях пошуку не мають повторюватись."
        ),
        FieldProblem(
            "locations.1.work_modes",
            "Для місця «valencia» обери хоч один формат: remote, hybrid чи onsite.",
        ),
    )
    assert world.get(world.alice) == FULL


def test_save_stamps_the_time_of_the_change(world: World) -> None:
    world.save(world.alice, TARGET)
    first = world.clock.now()
    world.clock.advance(timedelta(minutes=5))
    world.save(world.alice, RULES)
    assert world.saved_at[world.alice.user_id] == first + timedelta(minutes=5)


def test_replace_profile_replaces_every_section(world: World) -> None:
    world.replace(world.alice, FULL)
    other = ProfileData(
        target=TargetData(roles=("QA",)), contacts=ContactsData(full_name="Katya")
    )
    assert world.replace(world.alice, other) == other
    assert world.get(world.alice) == other


def test_replace_profile_reports_problems_of_every_section(world: World) -> None:
    with pytest.raises(InvalidFields) as raised:
        world.replace(
            world.alice,
            ProfileData(
                target=TargetData(min_salary_eur=-1),
                locations=LocationsData(
                    locations=(LocationData(place="Madrid", work_modes=()),)
                ),
                contacts=ContactsData(email="nope"),
            ),
        )
    assert [problem.field for problem in raised.value.problems] == [
        "target.min_salary_eur",
        "locations.locations.0.work_modes",
        "contacts.email",
    ]
    assert world.store == {}


def test_a_profile_is_visible_only_to_its_owner(world: World) -> None:
    world.replace(world.alice, FULL)
    assert world.get(world.bob) == ProfileData()


def test_saving_for_one_user_does_not_touch_another(world: World) -> None:
    world.replace(world.alice, FULL)
    world.save(world.bob, TargetData(roles=("Designer",)))
    assert world.get(world.alice) == FULL
    assert world.get(world.bob).target.roles == ("Designer",)
