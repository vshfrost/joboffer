"""Use cases профілю. REST і MCP викликають саме їх — правила валідації в одному місці.

Збереження розділу змінює лише його поля, тож розділи, відкриті в різних вкладках, не
перезаписують один одного застарілими значеннями. Одночасні правки того самого розділу —
остання перемагає (як у v1).
"""

from collections.abc import Callable
from datetime import datetime

from application.contracts.actor import Actor
from application.contracts.profile import (
    ContactsData,
    LocationData,
    LocationsData,
    ProfileData,
    RulesData,
    SectionData,
    TargetData,
)
from application.ports.clock import Clock
from application.ports.profile import ProfileUnitOfWork
from domain.profile.contacts import Contacts, ContactsDraft
from domain.profile.locations import LocationDraft, Locations
from domain.profile.modes import Seniority, WorkMode
from domain.profile.profile import Profile, ProfileSection
from domain.profile.rules import Rules
from domain.profile.target import Target
from domain.shared.errors import FieldProblem, InvalidFields


class ProfileUseCases:
    def __init__(
        self, unit_of_work: Callable[[], ProfileUnitOfWork], clock: Clock
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def get_profile(self, actor: Actor) -> ProfileData:
        """Профілю ще нема — порожній (рядок у сховищі з'являється при першому збереженні)."""
        async with self._unit_of_work() as uow:
            return profile_data(await uow.profiles.get(actor.user_id))

    async def save_section(self, actor: Actor, data: SectionData) -> ProfileData:
        """Змінює лише розділ `data`; повертає профіль цілком. Некоректні дані — `InvalidFields`."""
        section = _section(data)
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            before = await uow.profiles.get(actor.user_id)
            await uow.profiles.save_section(actor.user_id, section, now)
            saved = await uow.profiles.get(actor.user_id)
            await self._mark_if_changed(uow, actor, before, saved, now)
            await uow.commit()
        return profile_data(saved)

    async def replace_profile(self, actor: Actor, data: ProfileData) -> ProfileData:
        """Замінює профіль цілком; помилки всіх розділів — разом, з іменем розділу в шляху поля."""
        profile = _profile(data)
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            before = await uow.profiles.get(actor.user_id)
            await uow.profiles.replace(actor.user_id, profile, now)
            saved = await uow.profiles.get(actor.user_id)
            await self._mark_if_changed(uow, actor, before, saved, now)
            await uow.commit()
        return profile_data(saved)

    @staticmethod
    async def _mark_if_changed(
        uow: ProfileUnitOfWork,
        actor: Actor,
        before: Profile,
        after: Profile,
        now: datetime,
    ) -> None:
        """Зміна цілі, локацій чи правил (не контактів, не збереження без змін) старить аналізи."""
        if before.changes_analysis_inputs(after):
            await uow.profiles.mark_analysis_inputs_changed(actor.user_id, now)


def _section(data: SectionData) -> ProfileSection:
    if isinstance(data, TargetData):
        return Target.parse(
            roles=data.roles,
            seniority=data.seniority,
            min_salary_eur=data.min_salary_eur,
            target_domains=data.target_domains,
        )
    if isinstance(data, LocationsData):
        return Locations.parse(
            work_modes=data.work_modes,
            locations=[
                LocationDraft(
                    place=item.place, aliases=item.aliases, work_modes=item.work_modes
                )
                for item in data.locations
            ],
            include_unknown_mode=data.include_unknown_mode,
            relocation=data.relocation,
        )
    if isinstance(data, RulesData):
        return Rules.parse(
            title_keywords=data.title_keywords,
            title_exclude=data.title_exclude,
            stop_words=data.stop_words,
        )
    return Contacts.parse(
        ContactsDraft(
            full_name=data.full_name,
            email=data.email,
            phone=data.phone,
            linkedin_url=data.linkedin_url,
            city=data.city,
            github_url=data.github_url,
            work_authorization=data.work_authorization,
        )
    )


def _profile(data: ProfileData) -> Profile:
    problems: list[FieldProblem] = []
    sections: list[ProfileSection] = []
    for name, part in (
        ("target", data.target),
        ("locations", data.locations),
        ("rules", data.rules),
        ("contacts", data.contacts),
    ):
        try:
            sections.append(_section(part))
        except InvalidFields as error:
            problems += [
                FieldProblem(f"{name}.{problem.field}", problem.message)
                for problem in error.problems
            ]
    if problems:
        raise InvalidFields(problems)
    profile = Profile()
    for section in sections:
        profile = profile.with_section(section)
    return profile


def profile_data(profile: Profile) -> ProfileData:
    """Домен → примітиви; формати й рівні — у фіксованому порядку enum-ів, як у v1."""
    target, locations = profile.target, profile.locations
    return ProfileData(
        target=TargetData(
            roles=target.roles,
            seniority=tuple(
                level.value for level in Seniority if level in target.seniority
            ),
            min_salary_eur=target.min_salary_eur,
            target_domains=target.target_domains,
        ),
        locations=LocationsData(
            work_modes=_modes(locations.work_modes),
            locations=tuple(
                LocationData(
                    place=item.place,
                    aliases=item.aliases,
                    work_modes=_modes(item.work_modes),
                )
                for item in locations.locations
            ),
            include_unknown_mode=locations.include_unknown_mode,
            relocation=locations.relocation,
        ),
        rules=RulesData(
            title_keywords=profile.rules.title_keywords,
            title_exclude=profile.rules.title_exclude,
            stop_words=profile.rules.stop_words,
        ),
        contacts=ContactsData(
            full_name=profile.contacts.full_name,
            email=profile.contacts.email,
            phone=profile.contacts.phone,
            linkedin_url=profile.contacts.linkedin_url,
            city=profile.contacts.city,
            github_url=profile.contacts.github_url,
            work_authorization=profile.contacts.work_authorization,
        ),
    )


def _modes(modes: frozenset[WorkMode]) -> tuple[str, ...]:
    return tuple(mode.value for mode in WorkMode if mode in modes)
