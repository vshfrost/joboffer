"""«Уже не проходять фільтр»: які збережені вакансії й чому профіль їх уже не взяв би."""

from datetime import UTC, datetime
from uuid import UUID

from domain.jobs.ids import JobId
from domain.jobs.job import Job
from domain.profile.profile import Profile
from domain.profile.rules import Rules
from domain.sources.filtered import FilteredJob, filtered_jobs
from domain.sources.filtering import Skip

PROFILE = Profile(rules=Rules(title_keywords=("backend",), title_exclude=("graduate",)))


def stored(number: int, title: str, **fields: object) -> Job:
    base: dict[str, object] = {
        "id": JobId(UUID(int=number)),
        "number": number,
        "source": "ats:greenhouse",
        "text": "Опис вакансії.",
        "url": f"https://acme.example/jobs/{number}",
        "title": title,
        "company": "Acme",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    return Job(**(base | fields))  # type: ignore[arg-type]


def test_failing_jobs_are_listed_with_number_title_company_and_reason_but_not_empty_ones() -> (
    None
):
    jobs = [
        stored(1, "Backend Engineer"),
        stored(2, "Product Manager"),
        stored(3, "Graduate Backend Engineer"),
        stored(4, "Product Owner", text="", location="Valencia"),
    ]

    assert filtered_jobs(jobs, PROFILE) == [
        FilteredJob(2, "Product Manager", "Acme", Skip.TITLE),
        FilteredJob(3, "Graduate Backend Engineer", "Acme", Skip.EXCLUDED),
    ]
