"""check_cv показує перший екран CV (посада, summary, перша група скілів, перший пункт кожної ролі) і
слова вакансії, що потрапили саме туди: так видно розміщення, а не лише наявність."""

from application.contracts.actor import Actor
from application.contracts.documents import (
    CheckData,
    CvData,
    CvEntryData,
    CvSectionData,
    FirstBulletData,
    FirstScreenData,
    SkillsGroupData,
)
from tests.unit.application.test_document_pdf_use_cases import seeded
from tests.unit.application.test_document_use_cases import (
    World,
    claim,
    cv_data,
    world,
)

__all__ = ["world"]


def cv(
    fact: int,
    *,
    summary: str = "Payments backend",
    skills: tuple[tuple[str, tuple[str, ...]], ...] = (),
    roles: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("Engineer · Acme", ("Built payment APIs",)),
    ),
) -> CvData:
    """CV: Experience з ролями (заголовок, пункти) і, якщо задано, Skills з групами (назва, пункти)."""
    sections = [
        CvSectionData(
            name="Experience",
            entries=tuple(
                CvEntryData(
                    heading=claim(heading, fact),
                    bullets=tuple(claim(text, fact) for text in bullets),
                )
                for heading, bullets in roles
            ),
        )
    ]
    if skills:
        sections.append(
            CvSectionData(
                name="Skills",
                entries=tuple(
                    CvEntryData(
                        heading=claim(label, fact),
                        bullets=tuple(claim(item, fact) for item in items),
                    )
                    for label, items in skills
                ),
            )
        )
    return CvData(
        headline=claim("Senior Backend Engineer", fact),
        summary=claim(summary, fact),
        sections=tuple(sections),
    )


def check(world: World, owner: Actor, number: int, data: CvData) -> CheckData:
    return world.portal.call(world.documents.check_cv, owner, number, data)


def screen(checked: CheckData) -> FirstScreenData:
    assert checked.first_screen is not None
    return checked.first_screen


def test_the_first_screen_has_the_headline_summary_first_skills_group_and_first_bullets(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    data = cv(
        fact,
        skills=(("Backend", ("Python", "Kafka")), ("Tools", ("Docker",))),
        roles=(
            ("Engineer · Acme", ("Built payment APIs", "Cut latency by 40%")),
            ("Developer · Beta", ("Wrote ETL jobs", "Ran on-call")),
        ),
    )

    checked = check(world, owner, number, data)

    assert checked.first_screen == FirstScreenData(
        headline="Senior Backend Engineer",
        summary="Payments backend",
        skills_group=SkillsGroupData(label="Backend", items=("Python", "Kafka")),
        first_bullets=(
            FirstBulletData(role="Engineer · Acme", text="Built payment APIs"),
            FirstBulletData(role="Developer · Beta", text="Wrote ETL jobs"),
        ),
        keywords=(),
    )


def test_a_keyword_in_the_summary_is_in_the_first_screen_keywords(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, keywords=["Kafka"])

    checked = check(world, owner, number, cv(fact, summary="Backend engineer on Kafka"))

    assert screen(checked).keywords == ("Kafka",)


def test_a_keyword_only_in_an_old_role_is_not_in_the_first_screen(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, keywords=["Kafka", "Go"])
    data = cv(
        fact,
        roles=(
            ("Engineer · Acme", ("Built payment APIs",)),
            ("Developer · Beta", ("Wrote ETL jobs", "Wrote Kafka consumers")),
        ),
    )

    checked = check(world, owner, number, data)

    assert screen(checked).keywords == ()
    assert checked.keywords is not None
    assert checked.keywords.covered == ("Kafka",)


def test_a_keyword_in_a_later_bullet_of_the_newest_role_is_not_in_the_first_screen(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, keywords=["Kafka"])
    data = cv(fact, roles=(("Engineer · Acme", ("Built payment APIs", "Ran Kafka")),))

    checked = check(world, owner, number, data)

    assert screen(checked).keywords == ()


def test_a_keyword_in_the_first_skills_group_counts_but_in_the_second_does_not(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, keywords=["Python", "Docker"])
    data = cv(fact, skills=(("Backend", ("Python",)), ("Tools", ("Docker",))))

    checked = check(world, owner, number, data)

    assert screen(checked).keywords == ("Python",)


def test_a_cv_without_skills_has_an_empty_group_and_no_error(world: World) -> None:
    owner, number, fact = seeded(world)

    checked = check(world, owner, number, cv_data(fact))

    assert screen(checked).skills_group == SkillsGroupData(label="", items=())
    assert checked.passed is True


def test_a_role_without_bullets_has_no_first_bullet(world: World) -> None:
    owner, number, fact = seeded(world)
    data = cv(
        fact,
        roles=(("Engineer · Acme", ("Built payment APIs",)), ("Intern · Old", ())),
    )

    checked = check(world, owner, number, data)

    assert screen(checked).first_bullets == (
        FirstBulletData(role="Engineer · Acme", text="Built payment APIs"),
    )


def test_a_cv_with_an_unconfirmed_fact_has_no_first_screen(world: World) -> None:
    owner, number, _ = seeded(world)

    checked = check(world, owner, number, cv_data(999))

    assert checked.first_screen is None
