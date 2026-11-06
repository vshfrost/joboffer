"""Кар'єрна ціль: нормалізація й правила v1."""

import pytest

from domain.profile.modes import Seniority
from domain.profile.target import Target
from domain.shared.errors import FieldProblem, InvalidFields


def parse(**overrides: object) -> Target:
    fields: dict[str, object] = {
        "roles": [],
        "seniority": [],
        "min_salary_eur": None,
        "target_domains": [],
    }
    fields.update(overrides)
    return Target.parse(**fields)  # type: ignore[arg-type]


def problems(**overrides: object) -> tuple[FieldProblem, ...]:
    with pytest.raises(InvalidFields) as raised:
        parse(**overrides)
    return raised.value.problems


def test_an_empty_target_is_valid() -> None:
    assert parse() == Target()


def test_roles_are_trimmed_without_blanks_and_repeats() -> None:
    target = parse(roles=["  Backend Engineer ", "", "backend engineer", "SRE"])
    assert target.roles == ("Backend Engineer", "SRE")


def test_seniority_is_a_set_of_known_levels() -> None:
    target = parse(seniority=["senior", "lead", "senior"])
    assert target.seniority == frozenset({Seniority.SENIOR, Seniority.LEAD})


def test_unknown_seniority_is_rejected() -> None:
    assert problems(seniority=["senior", "wizard"]) == (
        FieldProblem("seniority", "Невідомий рівень."),
    )


def test_salary_is_kept_as_given() -> None:
    assert parse(min_salary_eur=60000).min_salary_eur == 60000
    assert parse(min_salary_eur=0).min_salary_eur == 0


def test_negative_salary_is_rejected() -> None:
    assert problems(min_salary_eur=-1) == (
        FieldProblem("min_salary_eur", "Мінімальна зарплата не може бути від'ємною."),
    )


def test_target_domains_are_normalized_like_roles() -> None:
    target = parse(target_domains=[" fintech ", "Fintech", "payments"])
    assert target.target_domains == ("fintech", "payments")


@pytest.mark.parametrize(
    "domains",
    [[f"domain-{number}" for number in range(21)], ["d" * 101]],
)
def test_too_many_or_too_long_domains_are_rejected(domains: list[str]) -> None:
    assert problems(target_domains=domains) == (
        FieldProblem(
            "target_domains", "Цільових доменів — до 20, кожен до 100 символів."
        ),
    )


def test_twenty_domains_of_one_hundred_characters_fit() -> None:
    domains = [f"{number:02d}" + "x" * 98 for number in range(20)]
    assert len(parse(target_domains=domains).target_domains) == 20


def test_every_problem_is_reported_not_only_the_first() -> None:
    found = problems(seniority=["wizard"], min_salary_eur=-5)
    assert {problem.field for problem in found} == {"seniority", "min_salary_eur"}


def test_salary_above_the_storage_limit_is_rejected() -> None:
    assert problems(min_salary_eur=2_147_483_648) == (
        FieldProblem("min_salary_eur", "Мінімальна зарплата — до 2147483647 EUR."),
    )


def test_salary_at_the_storage_limit_fits() -> None:
    assert parse(min_salary_eur=2_147_483_647).min_salary_eur == 2_147_483_647
