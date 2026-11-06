"""Підтверджені факти для документів: вибірка в порядку видів і перевірка номерів. Тексти — як у v1."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from domain.facts.fact import Fact, FactKind
from domain.facts.ids import FactId
from domain.facts.library import confirmed, require_confirmed
from domain.shared.errors import InvalidValue

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def _fact(number: int, kind: FactKind, *, confirmed: bool) -> Fact:
    return Fact(
        FactId(UUID(int=number)), number, kind, f"f{number}", confirmed, NOW, NOW
    )


FACTS = [
    _fact(1, FactKind.SKILL, confirmed=True),
    _fact(2, FactKind.SKILL, confirmed=False),
    _fact(3, FactKind.EXPERIENCE, confirmed=True),
    _fact(4, FactKind.LANGUAGE, confirmed=True),
    _fact(5, FactKind.SKILL, confirmed=True),
]


def test_confirmed_facts_go_by_kind_then_by_number() -> None:
    assert [fact.number for fact in confirmed(FACTS)] == [3, 1, 5, 4]


def test_no_confirmed_facts_is_an_empty_list() -> None:
    assert confirmed([FACTS[1]]) == []


def test_confirmed_numbers_pass() -> None:
    require_confirmed(FACTS, {1, 3, 5})


def test_no_numbers_pass() -> None:
    require_confirmed(FACTS, set())


def test_unknown_numbers_are_named_in_order() -> None:
    with pytest.raises(InvalidValue) as error:
        require_confirmed(FACTS, {42, 9})

    assert error.value.message == "Факти не знайдено: #9, #42."
    assert error.value.field == "fact_ids"


def test_unconfirmed_numbers_are_named_in_order() -> None:
    with pytest.raises(InvalidValue) as error:
        require_confirmed(FACTS, {2, 1})

    assert error.value.message == (
        "Факти не підтверджені: #2 — спершу користувач їх підтверджує."
    )
    assert error.value.field == "fact_ids"


def test_unknown_numbers_are_reported_before_unconfirmed() -> None:
    with pytest.raises(InvalidValue) as error:
        require_confirmed(FACTS, {2, 42})

    assert error.value.message == "Факти не знайдено: #42."
