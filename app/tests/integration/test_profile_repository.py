"""PostgresProfiles на справжній базі: розділи змінюються окремо, порядок локацій, обмеження, схема для ETL."""

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.identity.email import Email
from domain.identity.ids import UserId
from domain.identity.password import PasswordHash
from domain.identity.user import DisplayName, User
from domain.profile.contacts import Contacts, ContactsDraft
from domain.profile.locations import LocationDraft, Locations
from domain.profile.profile import Profile, ProfileSection
from domain.profile.rules import Rules
from domain.profile.target import Target
from infrastructure.db.unit_of_work import UnitOfWorkFactory, unit_of_work_factory

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
LATER = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
ALICE = UserId(UUID(int=1))
BOB = UserId(UUID(int=2))

# Усі поля таблиці `preferences` v1 (крім ключа й часу): ETL у B12 переносить їх без втрат.
V1_PROFILE_COLUMNS = {
    "roles",
    "work_modes",
    "include_unknown_mode",
    "relocation",
    "target_domains",
    "seniority",
    "min_salary_eur",
    "stop_words",
    "title_keywords",
    "title_exclude",
    "full_name",
    "email",
    "phone",
    "linkedin_url",
    "city",
    "github_url",
    "work_authorization",
}


def target(**fields: object) -> Target:
    base: dict[str, object] = {
        "roles": ["Backend Engineer"],
        "seniority": ["senior"],
        "min_salary_eur": 70000,
        "target_domains": ["fintech"],
    }
    return Target.parse(**(base | fields))  # type: ignore[arg-type]


def locations(*places: str, relocation: bool = True) -> Locations:
    return Locations.parse(
        work_modes=["remote", "hybrid"],
        locations=[
            LocationDraft(
                place=place, aliases=(f"{place}-alias",), work_modes=("hybrid",)
            )
            for place in places
        ],
        include_unknown_mode=False,
        relocation=relocation,
    )


RULES = Rules.parse(
    title_keywords=["backend"], title_exclude=["junior"], stop_words=["crypto"]
)
CONTACTS = Contacts.parse(
    ContactsDraft(
        full_name="Taras",
        email="taras@example.com",
        phone="+34 600 000 000",
        linkedin_url="https://linkedin.com/in/taras",
        city="Valencia",
        github_url="https://github.com/taras",
        work_authorization="Spain / EU work authorization",
    )
)


def full_profile(*places: str) -> Profile:
    return Profile(
        target=target(),
        locations=locations(*(places or ("Valencia", "Madrid"))),
        rules=RULES,
        contacts=CONTACTS,
    )


@pytest.fixture
def uow(portal: BlockingPortal, engine: AsyncEngine) -> UnitOfWorkFactory:
    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
        factory = unit_of_work_factory(engine)
        async with factory() as tx:
            for number, user_id in enumerate((ALICE, BOB), start=1):
                await tx.users.add(
                    User.register(
                        id=user_id,
                        email=Email(f"user{number}@example.com"),
                        display_name=DisplayName(f"User {number}"),
                        password_hash=PasswordHash("$test$"),
                        now=NOW,
                    )
                )
            await tx.commit()

    portal.call(prepare)
    return unit_of_work_factory(engine)


async def _get(uow: UnitOfWorkFactory, user_id: UserId) -> Profile:
    async with uow() as tx:
        return await tx.profiles.get(user_id)


async def _replace(
    uow: UnitOfWorkFactory, user_id: UserId, profile: Profile, now: datetime = NOW
) -> None:
    async with uow() as tx:
        await tx.profiles.replace(user_id, profile, now)
        await tx.commit()


async def _save(
    uow: UnitOfWorkFactory,
    user_id: UserId,
    section: ProfileSection,
    now: datetime = NOW,
) -> None:
    async with uow() as tx:
        await tx.profiles.save_section(user_id, section, now)
        await tx.commit()


async def _scalar(engine: AsyncEngine, sql: str) -> object:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar()


def test_a_user_without_a_row_gets_an_empty_profile(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    assert portal.call(_get, uow, ALICE) == Profile()
    assert portal.call(_scalar, engine, "SELECT count(*) FROM profiles") == 0
    assert portal.call(_scalar, engine, "SELECT count(*) FROM profile_locations") == 0


def test_a_full_profile_roundtrips(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    profile = full_profile()
    portal.call(_replace, uow, ALICE, profile)
    assert portal.call(_get, uow, ALICE) == profile


def test_saving_a_section_of_a_new_user_creates_the_row_with_empty_others(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_save, uow, ALICE, RULES)
    assert portal.call(_get, uow, ALICE) == Profile(rules=RULES)


@pytest.mark.parametrize(
    "section",
    [
        pytest.param(target(roles=["SRE"], min_salary_eur=None), id="target"),
        pytest.param(locations("Cádiz", relocation=False), id="locations"),
        pytest.param(
            Rules.parse(title_keywords=[], title_exclude=[], stop_words=["gambling"]),
            id="rules",
        ),
        pytest.param(
            Contacts.parse(ContactsDraft(**{**asdict(CONTACTS), "city": "Madrid"})),
            id="contacts",
        ),
    ],
)
def test_saving_a_section_leaves_the_other_sections_untouched(
    portal: BlockingPortal, uow: UnitOfWorkFactory, section: ProfileSection
) -> None:
    before = full_profile()
    portal.call(_replace, uow, ALICE, before)
    portal.call(_save, uow, ALICE, section)
    assert portal.call(_get, uow, ALICE) == before.with_section(section)


def test_locations_keep_their_order(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    places = ["Madrid", "Barcelona", "Valencia", "Alicante"]
    portal.call(_save, uow, ALICE, locations(*places))
    saved = portal.call(_get, uow, ALICE)
    assert [location.place for location in saved.locations.locations] == places


def test_saving_fewer_locations_removes_the_rest(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_save, uow, ALICE, locations("Madrid", "Valencia", "Alicante"))
    portal.call(_save, uow, ALICE, locations("Valencia"))
    saved = portal.call(_get, uow, ALICE)
    assert [location.place for location in saved.locations.locations] == ["Valencia"]


def test_a_place_can_move_to_another_position(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_save, uow, ALICE, locations("Madrid", "Valencia"))
    portal.call(_save, uow, ALICE, locations("Valencia", "Madrid"))
    saved = portal.call(_get, uow, ALICE)
    assert [location.place for location in saved.locations.locations] == [
        "Valencia",
        "Madrid",
    ]


def test_two_users_may_have_the_same_place(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_save, uow, ALICE, locations("Valencia"))
    portal.call(_save, uow, BOB, locations("Valencia"))
    assert portal.call(_get, uow, BOB).locations.locations[0].place == "Valencia"


def test_profiles_of_different_users_are_independent(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_replace, uow, ALICE, full_profile())
    portal.call(_save, uow, BOB, target(roles=["Designer"]))
    assert portal.call(_get, uow, ALICE) == full_profile()
    assert portal.call(_get, uow, BOB).target.roles == ("Designer",)
    assert portal.call(_get, uow, BOB).contacts == Contacts()


def test_the_time_of_the_last_change_is_stored(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_save, uow, ALICE, RULES, NOW)
    portal.call(_save, uow, ALICE, CONTACTS, LATER)
    stored = portal.call(_scalar, engine, "SELECT updated_at FROM profiles")
    assert stored == LATER


def test_an_unsaved_transaction_changes_nothing(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def forget() -> None:
        async with uow() as tx:
            await tx.profiles.replace(ALICE, full_profile(), NOW)

    portal.call(forget)
    assert portal.call(_get, uow, ALICE) == Profile()


def test_concurrent_saves_of_locations_do_not_collide(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    first, second = locations("Madrid", "Valencia"), locations("Valencia", "Madrid")

    async def race() -> None:
        await asyncio.gather(
            *(_save(uow, ALICE, section) for section in (first, second) * 4)
        )

    portal.call(race)
    saved = portal.call(_get, uow, ALICE).locations
    assert saved in (first, second)


def test_deleting_a_user_deletes_the_profile_and_its_locations(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_replace, uow, ALICE, full_profile())

    async def delete() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM users WHERE id = :id"), {"id": ALICE.value}
            )

    portal.call(delete)
    assert portal.call(_scalar, engine, "SELECT count(*) FROM profiles") == 0
    assert portal.call(_scalar, engine, "SELECT count(*) FROM profile_locations") == 0


def test_the_schema_holds_every_field_of_the_v1_profile(
    portal: BlockingPortal, engine: AsyncEngine
) -> None:
    async def columns(table: str) -> set[str]:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
                ),
                {"t": table},
            )
            return set(rows.scalars())

    assert portal.call(columns, "profiles") >= V1_PROFILE_COLUMNS
    assert {"place", "aliases", "work_modes", "position"} <= portal.call(
        columns, "profile_locations"
    )


def test_the_largest_v1_profile_fits_the_schema(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    drafts = [
        LocationDraft(
            place=f"{number:02d}" + "p" * 98,
            aliases=tuple(f"{index:02d}" + "a" * 98 for index in range(20)),
            work_modes=("remote", "hybrid", "onsite"),
        )
        for number in range(50)
    ]
    profile = Profile(
        target=Target.parse(
            roles=[f"role {number}" for number in range(500)],
            seniority=["junior", "middle", "senior", "lead", "principal"],
            min_salary_eur=2_000_000_000,
            target_domains=[f"{number:02d}" + "d" * 98 for number in range(20)],
        ),
        locations=Locations.parse(
            work_modes=["remote", "hybrid", "onsite"],
            locations=drafts,
            include_unknown_mode=False,
            relocation=True,
        ),
        rules=Rules.parse(
            title_keywords=[f"keyword {number}" for number in range(300)],
            title_exclude=[f"exclude {number}" for number in range(300)],
            stop_words=[f"stop {number}" for number in range(300)],
        ),
        contacts=Contacts.parse(
            ContactsDraft(
                full_name="n" * 200,
                email="e" * 180 + "@example.com",
                phone="1" * 200,
                linkedin_url="https://" + "l" * 190,
                city="c" * 200,
                github_url="https://" + "g" * 190,
                work_authorization="w" * 200,
            )
        ),
    )
    portal.call(_replace, uow, ALICE, profile)
    assert portal.call(_get, uow, ALICE) == profile


def test_the_database_rejects_a_negative_salary(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    async def insert() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO profiles (user_id, min_salary_eur, updated_at) VALUES (:id, -1, now())"
                ),
                {"id": ALICE.value},
            )

    with pytest.raises(IntegrityError):
        portal.call(insert)


def test_the_database_rejects_a_place_repeated_in_another_case(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_save, uow, ALICE, locations("Valencia"))

    async def insert() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO profile_locations (user_id, position, place, aliases, work_modes)"
                    " VALUES (:id, 1, 'VALENCIA', '{}', '{remote}')"
                ),
                {"id": ALICE.value},
            )

    with pytest.raises(IntegrityError):
        portal.call(insert)


@pytest.mark.parametrize("modes", [[], ["office"], ["remote", "office"]])
def test_the_database_rejects_a_location_without_known_modes(
    portal: BlockingPortal,
    uow: UnitOfWorkFactory,
    engine: AsyncEngine,
    modes: list[str],
) -> None:
    portal.call(_save, uow, ALICE, locations("Valencia"))

    async def insert() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO profile_locations (user_id, position, place, aliases, work_modes)"
                    " VALUES (:id, 1, 'Madrid', '{}', CAST(:modes AS text[]))"
                ),
                {"id": ALICE.value, "modes": modes},
            )

    with pytest.raises(IntegrityError):
        portal.call(insert)


def test_saving_an_empty_locations_section_removes_every_place(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_save, uow, ALICE, locations("Madrid", "Valencia"))
    portal.call(_save, uow, ALICE, locations())
    assert portal.call(_get, uow, ALICE).locations.locations == ()
