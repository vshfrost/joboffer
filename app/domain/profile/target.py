"""Кар'єрна ціль: ролі, рівні, мінімальна зарплата, цільові домени."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self

from domain.profile.modes import Seniority, parse_members
from domain.profile.text import unique_lines
from domain.shared.problems import Problems

MAX_DOMAINS = 20
MAX_DOMAIN_LENGTH = 100
# Верхня межа збігається з типом колонки (int4): більше не збережеться.
MAX_SALARY_EUR = 2_147_483_647


@dataclass(frozen=True, slots=True)
class Target:
    roles: tuple[str, ...] = ()
    seniority: frozenset[Seniority] = frozenset()
    min_salary_eur: int | None = None
    target_domains: tuple[str, ...] = ()

    @classmethod
    def parse(
        cls,
        *,
        roles: Sequence[str],
        seniority: Sequence[str],
        min_salary_eur: int | None,
        target_domains: Sequence[str],
    ) -> Self:
        problems = Problems()
        levels = parse_members(Seniority, seniority)
        if levels is None:
            problems.add("seniority", "Невідомий рівень.")
        if min_salary_eur is not None and min_salary_eur < 0:
            problems.add(
                "min_salary_eur", "Мінімальна зарплата не може бути від'ємною."
            )
        if min_salary_eur is not None and min_salary_eur > MAX_SALARY_EUR:
            problems.add(
                "min_salary_eur", f"Мінімальна зарплата — до {MAX_SALARY_EUR} EUR."
            )
        domains = unique_lines(target_domains)
        if len(domains) > MAX_DOMAINS or any(
            len(domain) > MAX_DOMAIN_LENGTH for domain in domains
        ):
            problems.add(
                "target_domains",
                f"Цільових доменів — до {MAX_DOMAINS}, кожен до {MAX_DOMAIN_LENGTH} символів.",
            )
        problems.raise_if_any()
        return cls(
            roles=unique_lines(roles),
            seniority=levels or frozenset(),
            min_salary_eur=min_salary_eur,
            target_domains=domains,
        )
