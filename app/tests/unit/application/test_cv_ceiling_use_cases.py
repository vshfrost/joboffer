"""prepare_cv показує стелю одразу: скільки слів вакансії CV може покрити чесно (треба 90) і які слова
без факту. Старий аналіз без карти: стелі нема, бриф працює як раніше."""

from application.contracts.actor import Actor
from tests.support.facts import InMemoryFactUnitOfWork
from tests.unit.application.test_document_pdf_use_cases import seeded
from tests.unit.application.test_document_use_cases import World, world

__all__ = ["world"]


def numbered(count: int) -> list[str]:
    return [f"w{number:02d}" for number in range(count)]


def confirm_fact(world: World, owner: Actor, number: int) -> None:
    async def run() -> None:
        async with InMemoryFactUnitOfWork(world.facts_store) as uow:
            await uow.facts.confirm(owner.user_id, [number], world.clock.now())
            await uow.commit()

    world.portal.call(run)


def test_18_of_20_words_backed_show_ceiling_90_and_name_the_two_requirements(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    words = numbered(20)
    world.analyse(
        owner,
        number,
        keywords=words,
        keyword_facts={word: [fact] for word in words[:18]},
    )

    ceiling = world.prepare_cv(owner, number).ceiling

    assert ceiling is not None
    assert (ceiling.percent, ceiling.unbacked, ceiling.reaches_target) == (
        90,
        ("w18", "w19"),
        True,
    )


def test_ceiling_below_90_warns_with_the_words_without_facts(world: World) -> None:
    owner, number, fact = seeded(world)
    world.analyse(
        owner,
        number,
        keywords=["Python", "Kafka"],
        keyword_facts={"Python": [fact]},
    )

    ceiling = world.prepare_cv(owner, number).ceiling

    assert ceiling is not None
    assert (ceiling.percent, ceiling.unbacked, ceiling.reaches_target) == (
        50,
        ("Kafka",),
        False,
    )


def test_an_unconfirmed_fact_does_not_raise_the_ceiling(world: World) -> None:
    owner, number, fact = seeded(world)
    draft = world.fact(owner, "Kafka", confirmed=False)
    world.analyse(
        owner,
        number,
        keywords=["Python", "Kafka"],
        keyword_facts={"Python": [fact], "Kafka": [draft]},
    )

    ceiling = world.prepare_cv(owner, number).ceiling

    assert ceiling is not None
    assert ceiling.percent == 50


def test_a_new_confirmed_fact_raises_the_ceiling(world: World) -> None:
    owner, number, fact = seeded(world)
    kafka = world.fact(owner, "Kafka", confirmed=False)
    world.analyse(
        owner,
        number,
        keywords=["Python", "Kafka"],
        keyword_facts={"Python": [fact], "Kafka": [kafka]},
    )
    before = world.prepare_cv(owner, number).ceiling

    confirm_fact(world, owner, kafka)
    after = world.prepare_cv(owner, number).ceiling

    assert (before and before.percent, after and after.percent) == (50, 100)


def test_an_old_analysis_without_a_map_has_no_ceiling_and_the_brief_works(
    world: World,
) -> None:
    owner, number, _ = seeded(world)
    world.analyse(owner, number, keywords=["Python", "Kafka"])

    brief = world.prepare_cv(owner, number)

    assert brief.ceiling is None
    assert brief.analysis is not None
    assert brief.job.job_number == number


def test_a_job_not_analysed_has_no_ceiling(world: World) -> None:
    owner, number, _ = seeded(world)

    assert world.prepare_cv(owner, number).ceiling is None
