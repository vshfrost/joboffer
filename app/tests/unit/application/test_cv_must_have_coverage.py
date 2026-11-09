"""check_cv показує покриття must-have пунктів аналізу: агент каже, які факти стоять під пунктом (прямо
чи як аналог), сервер перевіряє, що факти справжні й підтверджені, а рядок CV на них спирається.
Метрики слів (keywords, gate) від цього не змінюються."""

import pytest

from application.contracts.actor import Actor
from application.contracts.documents import (
    CheckData,
    CvData,
    GateData,
    KeywordCoverageData,
    MustHaveCoverageData,
    MustHaveFactsData,
    MustHaveItemData,
)
from domain.documents.gate import GateStatus
from domain.documents.must_have import MustHaveStatus
from domain.shared.errors import InvalidValue
from tests.unit.application.test_document_pdf_use_cases import seeded
from tests.unit.application.test_document_use_cases import World, cv_data, world

__all__ = ["world"]

NO_ENTRY = "У must_have_facts немає запису для цього пункту."


def check(
    world: World,
    owner: Actor,
    number: int,
    cv: CvData,
    *entries: MustHaveFactsData,
) -> CheckData:
    return world.portal.call(world.documents.check_cv, owner, number, cv, None, entries)


def coverage(checked: CheckData) -> MustHaveCoverageData:
    assert checked.must_have_coverage is not None
    return checked.must_have_coverage


def entry(item: str, kind: str, *fact_ids: int) -> MustHaveFactsData:
    return MustHaveFactsData(item=item, fact_ids=fact_ids, kind=kind)


def not_cited(*fact_ids: int) -> str:
    return f"Жоден рядок CV не спирається на факти {list(fact_ids)}."


def not_confirmed(*fact_ids: int) -> str:
    return f"Факти {list(fact_ids)} не є підтвердженими фактами користувача."


def test_a_must_have_with_a_fact_that_a_cv_line_cites_is_covered(world: World) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, must_have=["Python backend"])

    checked = check(
        world, owner, number, cv_data(fact), entry("Python backend", "fact", fact)
    )

    assert coverage(checked) == MustHaveCoverageData(
        items=(
            MustHaveItemData(
                item="Python backend",
                status=MustHaveStatus.COVERED,
                fact_ids=(fact,),
                reason=None,
            ),
        ),
        unknown=(),
    )


def test_a_must_have_with_an_analogue_that_a_cv_line_cites_is_analogue(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, must_have=["gRPC"])

    checked = check(
        world, owner, number, cv_data(fact), entry("gRPC", "analogue", fact)
    )

    assert coverage(checked).items == (
        MustHaveItemData(
            item="gRPC",
            status=MustHaveStatus.ANALOGUE,
            fact_ids=(fact,),
            reason=None,
        ),
    )


def test_a_must_have_without_an_entry_is_missing(world: World) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, must_have=["Python backend", "Kafka"])

    checked = check(
        world, owner, number, cv_data(fact), entry("Python backend", "fact", fact)
    )

    assert [
        (i.item, i.status, i.fact_ids, i.reason) for i in coverage(checked).items
    ] == [
        ("Python backend", MustHaveStatus.COVERED, (fact,), None),
        ("Kafka", MustHaveStatus.MISSING, (), NO_ENTRY),
    ]


def test_without_must_have_facts_every_must_have_of_the_analysis_is_missing(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, must_have=["Python backend", "Kafka"])

    checked = check(world, owner, number, cv_data(fact))

    assert coverage(checked) == MustHaveCoverageData(
        items=(
            MustHaveItemData(
                item="Python backend",
                status=MustHaveStatus.MISSING,
                fact_ids=(),
                reason=NO_ENTRY,
            ),
            MustHaveItemData(
                item="Kafka",
                status=MustHaveStatus.MISSING,
                fact_ids=(),
                reason=NO_ENTRY,
            ),
        ),
        unknown=(),
    )
    assert checked.passed


def test_facts_that_no_cv_line_cites_leave_the_item_missing(world: World) -> None:
    owner, number, fact = seeded(world)
    other = world.fact(owner, "Kafka")
    world.analyse(owner, number, must_have=["Kafka"])

    checked = check(world, owner, number, cv_data(fact), entry("Kafka", "fact", other))

    assert coverage(checked).items == (
        MustHaveItemData(
            item="Kafka",
            status=MustHaveStatus.MISSING,
            fact_ids=(),
            reason=not_cited(other),
        ),
    )


def test_a_fact_id_that_does_not_exist_leaves_the_item_missing_with_the_reason(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, must_have=["Kafka"])

    checked = check(world, owner, number, cv_data(fact), entry("Kafka", "fact", 9999))

    assert coverage(checked).items == (
        MustHaveItemData(
            item="Kafka",
            status=MustHaveStatus.MISSING,
            fact_ids=(),
            reason=not_confirmed(9999),
        ),
    )


def test_a_fact_of_another_user_leaves_the_item_missing_with_the_reason(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    # Номери фактів — у межах користувача: у Боба потрібен номер, якого в власника нема.
    world.fact(world.bob, "Go")
    foreign = world.fact(world.bob, "Kafka")
    world.analyse(owner, number, must_have=["Kafka"])

    checked = check(
        world, owner, number, cv_data(fact), entry("Kafka", "fact", fact, foreign)
    )

    assert coverage(checked).items == (
        MustHaveItemData(
            item="Kafka",
            status=MustHaveStatus.MISSING,
            fact_ids=(),
            reason=not_confirmed(foreign),
        ),
    )


def test_an_unconfirmed_fact_leaves_the_item_missing_with_the_reason(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    draft = world.fact(owner, "Kafka", confirmed=False)
    world.analyse(owner, number, must_have=["Kafka"])

    checked = check(world, owner, number, cv_data(fact), entry("Kafka", "fact", draft))

    assert coverage(checked).items == (
        MustHaveItemData(
            item="Kafka",
            status=MustHaveStatus.MISSING,
            fact_ids=(),
            reason=not_confirmed(draft),
        ),
    )


def test_an_item_that_is_not_in_the_analysis_is_unknown_not_an_error(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, must_have=["Python backend"])

    checked = check(
        world,
        owner,
        number,
        cv_data(fact),
        entry("Python backend", "fact", fact),
        entry("Rust", "fact", fact),
    )

    assert checked.passed
    assert coverage(checked).unknown == ("Rust",)
    assert [i.item for i in coverage(checked).items] == ["Python backend"]


def test_the_item_is_matched_ignoring_case_and_extra_spaces(world: World) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, must_have=["Python backend"])

    checked = check(
        world, owner, number, cv_data(fact), entry(" python  BACKEND ", "fact", fact)
    )

    assert coverage(checked).unknown == ()
    assert [(i.item, i.status) for i in coverage(checked).items] == [
        ("Python backend", MustHaveStatus.COVERED)
    ]


def test_a_fact_entry_wins_over_an_analogue_entry_of_the_same_item(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, must_have=["Python backend"])

    checked = check(
        world,
        owner,
        number,
        cv_data(fact),
        entry("Python backend", "analogue", fact),
        entry("Python backend", "fact", fact),
    )

    assert [i.status for i in coverage(checked).items] == [MustHaveStatus.COVERED]


def test_a_cited_entry_counts_even_when_another_entry_of_the_item_is_not_cited(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    other = world.fact(owner, "Kafka")
    world.analyse(owner, number, must_have=["Python backend"])

    checked = check(
        world,
        owner,
        number,
        cv_data(fact),
        entry("Python backend", "fact", other),
        entry("Python backend", "analogue", fact),
    )

    assert [(i.status, i.fact_ids) for i in coverage(checked).items] == [
        (MustHaveStatus.ANALOGUE, (fact,))
    ]


def test_a_job_without_analysis_has_no_must_have_coverage_and_the_check_works(
    world: World,
) -> None:
    owner, number, fact = seeded(world)

    checked = check(world, owner, number, cv_data(fact), entry("Kafka", "fact", fact))

    assert checked.must_have_coverage is None
    assert checked.passed


def test_an_analysis_without_must_have_has_an_empty_coverage(world: World) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number)

    checked = check(world, owner, number, cv_data(fact), entry("Kafka", "fact", fact))

    assert coverage(checked) == MustHaveCoverageData(items=(), unknown=("Kafka",))


def test_a_cv_that_cannot_be_read_has_no_must_have_coverage(world: World) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, must_have=["Python backend"])

    checked = check(
        world, owner, number, cv_data(9999), entry("Python backend", "fact", fact)
    )

    assert not checked.passed
    assert checked.must_have_coverage is None


def test_an_unknown_kind_is_an_invalid_value(world: World) -> None:
    owner, number, fact = seeded(world)
    world.analyse(owner, number, must_have=["Python backend"])

    with pytest.raises(InvalidValue):
        check(
            world, owner, number, cv_data(fact), entry("Python backend", "maybe", fact)
        )


def test_the_keyword_numbers_and_the_gate_do_not_depend_on_the_must_have_facts(
    world: World,
) -> None:
    owner, number, fact = seeded(world)
    world.analyse(
        owner,
        number,
        must_have=["Python backend"],
        keywords=["payment APIs", "Kafka"],
        keyword_facts={"payment APIs": [fact], "Kafka": [fact]},
    )

    checked = check(
        world, owner, number, cv_data(fact), entry("Python backend", "fact", fact)
    )

    assert checked.keywords == KeywordCoverageData(
        covered=("payment APIs",), missing=("Kafka",), percent=50
    )
    assert checked.gate == GateData(
        status=GateStatus.FAILED,
        evidence_percent=50,
        evidence_missing=("Kafka",),
        coverage_percent=50,
    )
    assert checked.passed
