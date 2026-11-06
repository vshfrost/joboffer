"""Відповідь на прогалину: «є досвід» потребує фактів, «немає досвіду» — без фактів."""

import pytest

from domain.analysis.gap_answer import validate_answer
from domain.shared.errors import InvalidValue


def test_experience_without_facts_is_refused() -> None:
    with pytest.raises(InvalidValue) as error:
        validate_answer(has_experience=True, fact_count=0)
    assert error.value.field == "facts"
    assert error.value.message == (
        "Відповідь «є досвід» потребує хоча б одного факту — "
        "із формулюванням, яке користувач схвалив."
    )


def test_no_experience_with_facts_is_refused() -> None:
    with pytest.raises(InvalidValue) as error:
        validate_answer(has_experience=False, fact_count=1)
    assert error.value.field == "facts"
    assert error.value.message == "Відповідь «немає досвіду» не може мати фактів."


@pytest.mark.parametrize(
    ("has_experience", "fact_count"), [(True, 1), (True, 3), (False, 0)]
)
def test_a_consistent_answer_is_accepted(has_experience: bool, fact_count: int) -> None:
    validate_answer(has_experience=has_experience, fact_count=fact_count)
