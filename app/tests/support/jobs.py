"""In-memory адаптер jobs для core-тестів: та сама семантика, що в Postgres (номери, дублі, commit)."""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import TracebackType
from typing import Self

from domain.analysis.analysis import Analysis
from domain.analysis.gap_answer import GapAnswer
from domain.applications.application import (
    Application,
    ApplicationStatus,
    NewApplication,
)
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import Job, JobSummary, NewJob
from domain.jobs.linkedin import linkedin_job_url
from domain.jobs.search import JobSearch, JobTabCounts
from domain.shared.fingerprint import text_fingerprint
from domain.sources.dedup import RecentJob
from domain.triage.triage import Triage, TriageVerdict

SOURCE_PREFIXES = ("ats:", "rss:")
VERDICT_RANK = {
    TriageVerdict.ANALYSE: 0,
    TriageVerdict.MAYBE: 1,
    TriageVerdict.SKIP: 2,
}


@dataclass
class Store:
    jobs: dict[tuple[UserId, int], Job]
    counters: dict[UserId, int]
    hashes: dict[tuple[UserId, int], str | None]
    linkedin: dict[tuple[UserId, int], str | None]
    triage: dict[tuple[UserId, int], Triage]
    analyses: dict[tuple[UserId, int], Analysis]
    applications: dict[tuple[UserId, int], Application]
    # Відповіді на прогалини: (користувач, номер вакансії, відбиток тексту прогалини).
    gap_answers: dict[tuple[UserId, int, str], GapAnswer] = field(default_factory=dict)
    # Вакансії з тріажем `rules` і відбиток його вхідних даних; решта тріажу — `agent`.
    rules_hashes: dict[tuple[UserId, int], str] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> Self:
        return cls({}, {}, {}, {}, {}, {}, {})

    def copy(self) -> Self:
        return type(self)(
            dict(self.jobs),
            dict(self.counters),
            dict(self.hashes),
            dict(self.linkedin),
            dict(self.triage),
            dict(self.analyses),
            dict(self.applications),
            dict(self.gap_answers),
            dict(self.rules_hashes),
        )


class InMemoryJobs:
    def __init__(self, store: Store) -> None:
        self._s = store

    async def lock_additions(self, user_id: UserId) -> None:
        return None

    def _mine(self, user_id: UserId) -> list[Job]:
        found = [job for (owner, _), job in self._s.jobs.items() if owner == user_id]
        return sorted(found, key=lambda job: job.number)

    async def find_duplicate(self, user_id: UserId, job: NewJob) -> int | None:
        for mine in self._mine(user_id):
            key = (user_id, mine.number)
            same_text = job.fingerprint is not None and (
                self._s.hashes[key] == job.fingerprint
            )
            same_url = job.url is not None and mine.url == job.url
            same_linkedin = (
                job.linkedin_id is not None and self._s.linkedin[key] == job.linkedin_id
            )
            if same_text or same_url or same_linkedin:
                return mine.number
        return None

    async def find_linkedin(self, user_id: UserId, linkedin_id: str) -> int | None:
        for mine in self._mine(user_id):
            if self._s.linkedin[
                (user_id, mine.number)
            ] == linkedin_id or mine.url == linkedin_job_url(linkedin_id):
                return mine.number
        return None

    async def add(
        self,
        user_id: UserId,
        job_id: JobId,
        job: NewJob,
        now: datetime,
        number: int | None = None,
    ) -> int:
        counter = self._s.counters.get(user_id, 0)
        given = counter + 1 if number is None else number
        self._s.counters[user_id] = max(counter, given)
        key = (user_id, given)
        self._s.jobs[key] = Job(
            id=job_id,
            number=given,
            source=job.source,
            text=job.text,
            url=job.url,
            title=job.title,
            company=job.company,
            created_at=now,
            location=job.location,
        )
        self._s.hashes[key] = job.fingerprint
        self._s.linkedin[key] = job.linkedin_id
        return given

    async def recent(self, user_id: UserId, since: datetime) -> list[RecentJob]:
        return [
            RecentJob(job.number, job.company, job.title, job.needs_text)
            for job in self._mine(user_id)
            if job.created_at >= since
        ]

    async def complete_text(self, user_id: UserId, number: int, text: str) -> None:
        key = (user_id, number)
        job = self._s.jobs.get(key)
        if job is not None and job.text is None:
            self._s.jobs[key] = replace(job, text=text)
            self._s.hashes[key] = text_fingerprint(text)

    async def get(self, user_id: UserId, number: int) -> Job | None:
        return self._s.jobs.get((user_id, number))

    async def mark_opened(self, user_id: UserId, number: int, now: datetime) -> None:
        job = self._s.jobs.get((user_id, number))
        if job is not None and job.opened_at is None:
            self._s.jobs[(user_id, number)] = replace(job, opened_at=now)

    async def tab_counts(self, user_id: UserId) -> JobTabCounts:
        raise NotImplementedError(
            "Лічильники табів рахує лише Postgres: tests/integration/test_jobs_stages_http.py"
        )

    async def search(self, user_id: UserId, search: JobSearch) -> list[JobSummary]:
        if search.stage is not None:
            raise NotImplementedError(
                "Етапи вакансій рахує лише Postgres: tests/integration/test_jobs_stages_http.py"
            )
        rows = [
            job
            for job in self._mine(user_id)
            if job.dismissed == search.dismissed
            and (not search.needs_text or job.needs_text)
            and (search.source is None or job.source == search.source)
            and (search.since is None or job.created_at >= search.since)
            and (search.query is None or _matches(job, search.query))
        ]
        if search.hide_rejected:
            rows = [
                job
                for job in rows
                if (application := self._s.applications.get((user_id, job.number)))
                is None
                or application.status is not ApplicationStatus.REJECTED
            ]
        if search.work_mode is not None:
            rows = [
                job
                for job in rows
                if (analysis := self._s.analyses.get((user_id, job.number)))
                and analysis.analysis.work_mode is search.work_mode
            ]
        if search.triage_verdict is not None:
            rows = [
                job
                for job in rows
                if (triage := self._s.triage.get((user_id, job.number)))
                and triage.verdict is search.triage_verdict
            ]
        if search.statuses is not None:
            rows = [
                job
                for job in rows
                if (application := self._s.applications.get((user_id, job.number)))
                and application.status in search.statuses
            ]
        rows.sort(key=lambda job: self._order_key(user_id, job))
        return [self._summary(user_id, job) for job in rows[: search.limit]]

    def _order_key(self, user_id: UserId, job: Job) -> tuple[object, ...]:
        """Без тексту — наприкінці; проаналізовані першими (пройшли фільтри, за скором); далі за
        вердиктом тріажу (analyse → maybe → skip → без тріажу) і його скором; далі новіші першими."""
        analysis = self._s.analyses.get((user_id, job.number))
        triage = self._s.triage.get((user_id, job.number))
        return (
            job.needs_text,
            analysis is None,
            0 if analysis is None or analysis.filters_passed else 1,
            0 if analysis is None else -analysis.analysis.score,
            VERDICT_RANK[triage.verdict] if triage else len(VERDICT_RANK),
            -triage.score if triage else 1,
            -job.created_at.timestamp(),
            -job.number,
        )

    def _summary(self, user_id: UserId, job: Job) -> JobSummary:
        triage = self._s.triage.get((user_id, job.number))
        analysis = self._s.analyses.get((user_id, job.number))
        application = self._s.applications.get((user_id, job.number))
        return JobSummary(
            number=job.number,
            source=job.source,
            url=job.url,
            title=job.title,
            company=job.company,
            created_at=job.created_at,
            needs_text=job.needs_text,
            dismissed=job.dismissed,
            score=analysis.analysis.score if analysis else None,
            filters_passed=analysis.filters_passed if analysis else None,
            work_mode=analysis.analysis.work_mode if analysis else None,
            triage_score=triage.score if triage else None,
            triage_verdict=triage.verdict if triage else None,
            triage_reason=triage.reason if triage else None,
            status=application.status if application else None,
            is_new=job.is_new,
        )

    async def get_triage(self, user_id: UserId, number: int) -> Triage | None:
        return self._s.triage.get((user_id, number))

    async def sources(self, user_id: UserId) -> list[str]:
        return sorted({job.source for job in self._mine(user_id)})

    async def source_jobs(self, user_id: UserId) -> list[Job]:
        return [
            job
            for job in self._mine(user_id)
            if job.source.startswith(SOURCE_PREFIXES)
            and job.text is not None
            and not job.dismissed
            and (user_id, job.number) not in self._s.analyses
            and (user_id, job.number) not in self._s.applications
        ]

    async def dismiss(
        self, user_id: UserId, numbers: Sequence[int], reason: str, now: datetime
    ) -> None:
        for number in numbers:
            job = self._s.jobs.get((user_id, number))
            if job is not None and not job.dismissed:
                self._s.jobs[(user_id, number)] = replace(
                    job, dismissed_at=now, dismiss_reason=reason
                )

    async def restore(self, user_id: UserId, number: int) -> None:
        job = self._s.jobs.get((user_id, number))
        if job is not None:
            self._s.jobs[(user_id, number)] = replace(
                job, dismissed_at=None, dismiss_reason=None
            )


class InMemoryApplications:
    def __init__(self, store: Store) -> None:
        self._s = store

    async def get(self, user_id: UserId, job_number: int) -> Application | None:
        return self._s.applications.get((user_id, job_number))

    async def save(
        self, user_id: UserId, job_number: int, details: NewApplication, now: datetime
    ) -> Application:
        key = (user_id, job_number)
        if key not in self._s.jobs:
            raise LookupError(f"вакансії {job_number} нема")
        current = self._s.applications.get(key)
        saved = Application(
            job_number=job_number,
            status=ApplicationStatus.APPLIED if current is None else current.status,
            applied_on=details.applied_on,
            channel=details.channel,
            ats=details.ats,
            company_domains=details.company_domains,
            company_emails=details.company_emails,
            status_changed_at=now if current is None else current.status_changed_at,
            cv=details.cv,
        )
        self._s.applications[key] = saved
        return saved

    async def list_all(self, user_id: UserId) -> list[Application]:
        return [
            application
            for (owner, _), application in sorted(
                self._s.applications.items(), key=lambda item: item[0][1]
            )
            if owner == user_id
        ]

    async def set_status(
        self,
        user_id: UserId,
        job_number: int,
        status: ApplicationStatus,
        now: datetime,
    ) -> Application:
        key = (user_id, job_number)
        saved = replace(self._s.applications[key], status=status, status_changed_at=now)
        self._s.applications[key] = saved
        return saved


def _matches(job: Job, query: str) -> bool:
    needle = query.casefold()
    return any(
        needle in (value or "").casefold()
        for value in (job.title, job.company, job.text)
    )


class InMemoryJobUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(self, store: Store) -> None:
        self._store = store
        self._staged: Store | None = None

    @property
    def jobs(self) -> InMemoryJobs:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemoryJobs(self._staged)

    @property
    def applications(self) -> InMemoryApplications:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemoryApplications(self._staged)

    async def __aenter__(self) -> Self:
        self._staged = self._store.copy()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        self._store.jobs, self._store.counters = (
            self._staged.jobs,
            self._staged.counters,
        )
        self._store.hashes, self._store.linkedin = (
            self._staged.hashes,
            self._staged.linkedin,
        )
        self._store.triage = self._staged.triage
        self._store.analyses = self._staged.analyses
        self._store.applications = self._staged.applications
