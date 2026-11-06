"""Кроки першого запуску й підказки до них. Крок «зроблено» — лише за реальними даними
користувача, а не за позначкою «бачив»; підказка — окрема від кроку (її бачено або сховано)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domain.profile.profile import Profile
from domain.shared.errors import NotFound


class OnboardingStep(StrEnum):
    GOAL = "goal"
    LOCATIONS = "locations"
    CONTACTS = "contacts"
    CLAUDE = "claude"
    ORIGINAL_CV = "original_cv"
    PHOTO = "photo"
    MAIL = "mail"


OPTIONAL_STEPS = frozenset({OnboardingStep.PHOTO, OnboardingStep.MAIL})

# По одній підказці на крок, ключ підказки = ключ кроку.
TIP_KEYS = tuple(step.value for step in OnboardingStep)


@dataclass(frozen=True, slots=True, kw_only=True)
class Evidence:
    """Що в користувача є насправді."""

    profile: Profile
    claude_connected: bool
    has_original_cv: bool
    has_photo: bool
    has_mail_address: bool


@dataclass(frozen=True, slots=True)
class TipState:
    key: str
    seen_at: datetime
    dismissed_at: datetime | None = None


def completed_steps(evidence: Evidence) -> frozenset[OnboardingStep]:
    profile = evidence.profile
    done = {
        OnboardingStep.GOAL: bool(profile.target.roles),
        OnboardingStep.LOCATIONS: bool(profile.locations.locations),
        OnboardingStep.CONTACTS: bool(
            profile.contacts.full_name and profile.contacts.email
        ),
        OnboardingStep.CLAUDE: evidence.claude_connected,
        OnboardingStep.ORIGINAL_CV: evidence.has_original_cv,
        OnboardingStep.PHOTO: evidence.has_photo,
        OnboardingStep.MAIL: evidence.has_mail_address,
    }
    return frozenset(step for step, is_done in done.items() if is_done)


def check_tip_key(key: str) -> str:
    """Ключ відомої підказки; інакше `NotFound`."""
    if key not in TIP_KEYS:
        raise NotFound("Підказку не знайдено.")
    return key
