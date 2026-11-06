"""Профіль: порожнє значення за замовчуванням і заміна одного розділу."""

from domain.profile.contacts import Contacts
from domain.profile.locations import Locations
from domain.profile.modes import Seniority, WorkMode
from domain.profile.profile import Profile
from domain.profile.rules import Rules
from domain.profile.target import Target

TARGET = Target(roles=("SRE",), seniority=frozenset({Seniority.SENIOR}))
LOCATIONS = Locations(work_modes=frozenset({WorkMode.REMOTE}), relocation=True)
RULES = Rules(title_exclude=("Junior",))
CONTACTS = Contacts(full_name="Taras", email="taras@example.com")


def full() -> Profile:
    return Profile(target=TARGET, locations=LOCATIONS, rules=RULES, contacts=CONTACTS)


def test_an_empty_profile_has_no_restrictions() -> None:
    profile = Profile()
    assert profile.target == Target()
    assert profile.locations.locations == ()
    assert profile.locations.include_unknown_mode is True
    assert profile.rules.title_keywords == ()
    assert profile.contacts.email == ""


def test_with_target_replaces_only_the_target() -> None:
    other = Target(roles=("Backend",))
    updated = full().with_section(other)
    assert updated == Profile(
        target=other, locations=LOCATIONS, rules=RULES, contacts=CONTACTS
    )


def test_with_locations_replaces_only_the_locations() -> None:
    other = Locations(relocation=False)
    updated = full().with_section(other)
    assert updated == Profile(
        target=TARGET, locations=other, rules=RULES, contacts=CONTACTS
    )


def test_with_rules_replaces_only_the_rules() -> None:
    other = Rules(stop_words=("crypto",))
    updated = full().with_section(other)
    assert updated == Profile(
        target=TARGET, locations=LOCATIONS, rules=other, contacts=CONTACTS
    )


def test_with_contacts_replaces_only_the_contacts() -> None:
    other = Contacts(city="Valencia")
    updated = full().with_section(other)
    assert updated == Profile(
        target=TARGET, locations=LOCATIONS, rules=RULES, contacts=other
    )
