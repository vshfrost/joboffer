"""Команди й результати контексту profile: примітиви (значення будує use case)."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True, kw_only=True)
class TargetData:
    roles: tuple[str, ...] = ()
    seniority: tuple[str, ...] = ()
    min_salary_eur: int | None = None
    target_domains: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class LocationData:
    place: str
    aliases: tuple[str, ...] = ()
    work_modes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class LocationsData:
    work_modes: tuple[str, ...] = ()
    locations: tuple[LocationData, ...] = ()
    include_unknown_mode: bool = True
    relocation: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class RulesData:
    title_keywords: tuple[str, ...] = ()
    title_exclude: tuple[str, ...] = ()
    stop_words: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ContactsData:
    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    city: str = ""
    github_url: str = ""
    work_authorization: str = ""


type SectionData = TargetData | LocationsData | RulesData | ContactsData


@dataclass(frozen=True, slots=True, kw_only=True)
class ProfileData:
    """Профіль цілком: і команда (повна заміна), і результат читання."""

    target: TargetData = field(default_factory=TargetData)
    locations: LocationsData = field(default_factory=LocationsData)
    rules: RulesData = field(default_factory=RulesData)
    contacts: ContactsData = field(default_factory=ContactsData)
