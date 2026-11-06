"""Вакансії з джерел, які поточний профіль уже не взяв би: список для перегляду й приховування."""

from collections.abc import Iterable
from dataclasses import dataclass

from domain.jobs.job import Job
from domain.profile.profile import Profile
from domain.shared.errors import Conflict
from domain.sources.filtering import Skip, stored_skip_reason


@dataclass(frozen=True, slots=True)
class FilteredJob:
    """Збережена вакансія з джерела, що за поточним профілем уже не пройшла б фільтр."""

    number: int
    title: str | None
    company: str | None
    reason: Skip


class FilteredChanged(Conflict):
    """Список «уже не проходять фільтр» змінився відтоді, як користувач його бачив."""

    code = "filtered_changed"

    def __init__(self, stale: Iterable[int]) -> None:
        numbers = ", ".join(str(number) for number in stale)
        super().__init__(
            f"Список змінився: вакансії {numbers} уже не в ньому. "
            "Онови список і перевір його ще раз."
        )


def filtered_jobs(jobs: Iterable[Job], profile: Profile) -> list[FilteredJob]:
    """Які з вакансій джерел не пройшли б фільтр профілю й чому. Вакансія без тексту — не справа
    профілю (`EMPTY`): її тут нема."""
    found = []
    for job in jobs:
        reason = stored_skip_reason(job, profile)
        if reason is not None and reason is not Skip.EMPTY:
            found.append(FilteredJob(job.number, job.title, job.company, reason))
    return found
