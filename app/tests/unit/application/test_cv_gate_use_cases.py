"""check_cv показує гейт: два числа й чи пройдено. Гейт лише інформує: CV зберігається й коли його
не пройдено. Слова з фактом — із карти аналізу; непідтверджений чи видалений факт слово не підтверджує."""

from application.contracts.actor import Actor
from application.contracts.documents import CheckData, GateData
from domain.documents.gate import GateStatus
from tests.support.facts import InMemoryFactUnitOfWork
from tests.unit.application.test_document_pdf_use_cases import letter, seeded
from tests.unit.application.test_document_use_cases import World, cv_data, world

__all__ = ["world"]

# У CV з `cv_data`: «Senior Backend Engineer», «Payments backend», «Built payment APIs».


def check(world: World, owner: Actor, number: int, fact: int, **cv: str) -> CheckData:
    return world.portal.call(
        world.documents.check_cv, owner, number, cv_data(fact, **cv)
    )


def delete_fact(world: World, owner: Actor, number: int) -> None:
    async def run() -> None:
        async with InMemoryFactUnitOfWork(world.facts_store) as uow:
            await uow.facts.delete(owner.user_id, number)
            await uow.commit()

    world.portal.call(run)


def numbered(count: int) -> list[str]:
    return [f"w{number:02d}" for number in range(count)]


def test_all_backed_words_in_the_cv_give_the_first_number_100(world: World) -> None:
    owner, number, fact = seeded(world)
    world.analyse(
        owner,
        number,
        keywords=["payment APIs", "Senior"],
        keyword_facts={"payment APIs": [fact], "Senior": [fact]},
    )

    checked = check(world, owner, number, fact)

    assert checked.gate == GateData(
        status=GateStatus.PASSED,
        evidence_percent=100,
        evidence_missing=(),
        coverage_percent=100,
    )


def test_a_backed_word_missing_from_the_cv_is_below_100_and_named(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.analyse(
        owner,
        number,
        keywords=["payment APIs", "Kafka"],
        keyword_facts={"payment APIs": [fact], "Kafka": [fact]},
    )

    checked = check(world, owner, number, fact)

    assert checked.gate == GateData(
        status=GateStatus.FAILED,
        evidence_percent=50,
        evidence_missing=("Kafka",),
        coverage_percent=50,
    )


def test_an_unconfirmed_fact_does_not_back_a_word(world: World) -> None:
    owner, number, fact = seeded(world)
    draft = world.fact(owner, "Kafka", confirmed=False)
    world.analyse(
        owner,
        number,
        keywords=["payment APIs", "Kafka"],
        keyword_facts={"payment APIs": [fact], "Kafka": [draft]},
    )

    checked = check(world, owner, number, fact)

    assert checked.gate is not None
    assert (checked.gate.evidence_percent, checked.gate.evidence_missing) == (100, ())


def test_a_deleted_fact_does_not_back_a_word(world: World) -> None:
    owner, number, fact = seeded(world)
    gone = world.fact(owner, "Kafka")
    world.analyse(
        owner,
        number,
        keywords=["payment APIs", "Kafka"],
        keyword_facts={"payment APIs": [fact], "Kafka": [gone]},
    )
    delete_fact(world, owner, gone)

    checked = check(world, owner, number, fact)

    assert checked.gate is not None
    assert (checked.gate.evidence_percent, checked.gate.evidence_missing) == (100, ())


def test_18_of_20_keywords_in_the_cv_pass_the_threshold_90(world: World) -> None:
    owner, number, fact = seeded(world)
    words = numbered(20)
    world.analyse(owner, number, keywords=words, keyword_facts={"w00": [fact]})

    checked = check(world, owner, number, fact, summary=" ".join(words[:18]))

    assert checked.gate == GateData(
        status=GateStatus.PASSED,
        evidence_percent=100,
        evidence_missing=(),
        coverage_percent=90,
    )


def test_17_of_20_keywords_in_the_cv_do_not_pass(world: World) -> None:
    owner, number, fact = seeded(world)
    words = numbered(20)
    world.analyse(owner, number, keywords=words, keyword_facts={"w00": [fact]})

    checked = check(world, owner, number, fact, summary=" ".join(words[:17]))

    assert checked.gate is not None
    assert (checked.gate.coverage_percent, checked.gate.status) == (
        85,
        GateStatus.FAILED,
    )


def test_an_old_analysis_without_the_map_has_no_data_not_passed(world: World) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, keywords=["payment APIs"])

    checked = check(world, owner, number, fact)

    assert checked.gate == GateData(
        status=GateStatus.NO_DATA,
        evidence_percent=None,
        evidence_missing=(),
        coverage_percent=100,
    )


def test_a_job_not_analysed_has_no_data(world: World) -> None:
    owner, number, fact = seeded(world)

    checked = check(world, owner, number, fact)

    assert checked.gate == GateData(
        status=GateStatus.NO_DATA,
        evidence_percent=None,
        evidence_missing=(),
        coverage_percent=None,
    )


def test_a_cv_is_still_saved_when_the_gate_is_not_passed(world: World) -> None:
    owner, number, fact = seeded(world)
    world.analyse(
        owner,
        number,
        keywords=["Kafka"],
        keyword_facts={"Kafka": [fact]},
    )
    gate = check(world, owner, number, fact).gate
    assert gate is not None
    assert gate.status is GateStatus.FAILED

    saved = world.save_cv(owner, number, cv_data(fact))

    assert [
        (item.kind.value, item.version) for item in world.listed(owner, number)
    ] == [("cv", saved.version)]


def test_a_cover_letter_check_has_no_gate(world: World) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, keywords=["Kafka"], keyword_facts={"Kafka": [fact]})

    checked = world.portal.call(
        world.documents.check_cover_letter, owner, number, letter(fact)
    )

    assert checked.gate is None
