"""ProfileRepository на Postgres.

Розділ зберігається `INSERT … ON CONFLICT DO UPDATE` лише своїх колонок, тож інші розділи не
чіпаються. Апсерт рядка профілю ще й блокує його до кінця транзакції: одночасні збереження
локацій одного користувача йдуть по черзі, а не б'ються об первинний ключ.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.identity.ids import UserId
from domain.profile.contacts import Contacts
from domain.profile.locations import Locations, SearchLocation
from domain.profile.modes import Seniority, WorkMode
from domain.profile.profile import Profile, ProfileSection
from domain.profile.rules import Rules
from domain.profile.target import Target
from infrastructure.db.profile.tables import ProfileLocationRow, ProfileRow

type Columns = dict[str, Any]


class PostgresProfiles:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UserId) -> Profile:
        row = await self._session.scalar(
            select(ProfileRow)
            .where(ProfileRow.user_id == user_id.value)
            .execution_options(populate_existing=True)
        )
        if row is None:
            return Profile()
        places = await self._session.scalars(
            select(ProfileLocationRow)
            .where(ProfileLocationRow.user_id == user_id.value)
            .order_by(ProfileLocationRow.position)
            .execution_options(populate_existing=True)
        )
        return Profile(
            target=_target(row),
            locations=_locations(row, list(places)),
            rules=_rules(row),
            contacts=_contacts(row),
        )

    async def save_section(
        self, user_id: UserId, section: ProfileSection, now: datetime
    ) -> None:
        await self._upsert(user_id, _columns(section), now)
        if isinstance(section, Locations):
            await self._replace_locations(user_id, section.locations)

    async def replace(self, user_id: UserId, profile: Profile, now: datetime) -> None:
        columns: Columns = {}
        for section in (
            profile.target,
            profile.locations,
            profile.rules,
            profile.contacts,
        ):
            columns |= _columns(section)
        await self._upsert(user_id, columns, now)
        await self._replace_locations(user_id, profile.locations.locations)

    async def analysis_inputs_changed_at(self, user_id: UserId) -> datetime | None:
        return await self._session.scalar(
            select(ProfileRow.analysis_inputs_changed_at).where(
                ProfileRow.user_id == user_id.value
            )
        )

    async def mark_analysis_inputs_changed(
        self, user_id: UserId, now: datetime
    ) -> None:
        values = {"analysis_inputs_changed_at": now}
        await self._session.execute(
            pg_insert(ProfileRow)
            .values(user_id=user_id.value, updated_at=now, **values)
            .on_conflict_do_update(index_elements=[ProfileRow.user_id], set_=values)
        )

    async def _upsert(self, user_id: UserId, columns: Columns, now: datetime) -> None:
        values = columns | {"updated_at": now}
        await self._session.execute(
            pg_insert(ProfileRow)
            .values(user_id=user_id.value, **values)
            .on_conflict_do_update(index_elements=[ProfileRow.user_id], set_=values)
        )

    async def _replace_locations(
        self, user_id: UserId, locations: tuple[SearchLocation, ...]
    ) -> None:
        await self._session.execute(
            delete(ProfileLocationRow).where(
                ProfileLocationRow.user_id == user_id.value
            )
        )
        if locations:
            await self._session.execute(
                insert(ProfileLocationRow),
                [
                    {
                        "user_id": user_id.value,
                        "position": position,
                        "place": location.place,
                        "aliases": list(location.aliases),
                        "work_modes": _mode_names(location.work_modes),
                    }
                    for position, location in enumerate(locations)
                ],
            )


def _mode_names(modes: frozenset[WorkMode]) -> list[str]:
    return [mode.value for mode in WorkMode if mode in modes]


def _columns(section: ProfileSection) -> Columns:
    """Колонки `profiles`, що належать розділу (локації лежать у своїй таблиці)."""
    if isinstance(section, Target):
        return {
            "roles": list(section.roles),
            "seniority": [
                level.value for level in Seniority if level in section.seniority
            ],
            "min_salary_eur": section.min_salary_eur,
            "target_domains": list(section.target_domains),
        }
    if isinstance(section, Locations):
        return {
            "work_modes": _mode_names(section.work_modes),
            "include_unknown_mode": section.include_unknown_mode,
            "relocation": section.relocation,
        }
    if isinstance(section, Rules):
        return {
            "title_keywords": list(section.title_keywords),
            "title_exclude": list(section.title_exclude),
            "stop_words": list(section.stop_words),
        }
    return {
        "full_name": section.full_name,
        "email": section.email,
        "phone": section.phone,
        "linkedin_url": section.linkedin_url,
        "city": section.city,
        "github_url": section.github_url,
        "work_authorization": section.work_authorization,
    }


def _target(row: ProfileRow) -> Target:
    return Target(
        roles=tuple(row.roles),
        seniority=frozenset(Seniority(value) for value in row.seniority),
        min_salary_eur=row.min_salary_eur,
        target_domains=tuple(row.target_domains),
    )


def _locations(row: ProfileRow, places: list[ProfileLocationRow]) -> Locations:
    return Locations(
        work_modes=frozenset(WorkMode(value) for value in row.work_modes),
        locations=tuple(
            SearchLocation(
                place=place.place,
                aliases=tuple(place.aliases),
                work_modes=frozenset(WorkMode(value) for value in place.work_modes),
            )
            for place in places
        ),
        include_unknown_mode=row.include_unknown_mode,
        relocation=row.relocation,
    )


def _rules(row: ProfileRow) -> Rules:
    return Rules(
        title_keywords=tuple(row.title_keywords),
        title_exclude=tuple(row.title_exclude),
        stop_words=tuple(row.stop_words),
    )


def _contacts(row: ProfileRow) -> Contacts:
    return Contacts(
        full_name=row.full_name,
        email=row.email,
        phone=row.phone,
        linkedin_url=row.linkedin_url,
        city=row.city,
        github_url=row.github_url,
        work_authorization=row.work_authorization,
    )
