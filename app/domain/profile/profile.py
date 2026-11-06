"""Профіль користувача: чотири розділи, кожен зберігається окремо."""

from dataclasses import dataclass, field, replace
from typing import Self

from domain.profile.contacts import Contacts
from domain.profile.locations import Locations
from domain.profile.rules import Rules
from domain.profile.target import Target

type ProfileSection = Target | Locations | Rules | Contacts


@dataclass(frozen=True, slots=True)
class Profile:
    """Порожній профіль = значення за замовчуванням: «обмеження немає / не вказано»."""

    target: Target = field(default_factory=Target)
    locations: Locations = field(default_factory=Locations)
    rules: Rules = field(default_factory=Rules)
    contacts: Contacts = field(default_factory=Contacts)

    def changes_analysis_inputs(self, other: Self) -> bool:
        """Чи міняє перехід до `other` те, на чому тримається аналіз (ціль, локації, правила)."""
        return (
            self.target != other.target
            or self.locations != other.locations
            or self.rules != other.rules
        )

    def with_section(self, section: ProfileSection) -> Self:
        if isinstance(section, Target):
            return replace(self, target=section)
        if isinstance(section, Locations):
            return replace(self, locations=section)
        if isinstance(section, Rules):
            return replace(self, rules=section)
        return replace(self, contacts=section)
