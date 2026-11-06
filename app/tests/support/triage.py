"""In-memory адаптер triage для core-тестів: та сама семантика, що в Postgres (кандидати, upsert, commit).

Ділить `Store` із фейком вакансій: тріаж бачить ті самі вакансії, що й список.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self

from domain.applications.application import CLOSED_STATUSES
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import Job
from domain.profile.profile import Profile
from domain.triage.ids import TriageId
from domain.triage.scoring import inputs_hash
from domain.triage.triage import Triage, TriageEntry, TriageSource, TriageVerdict
from tests.support.analysis import InMemoryAnalyses
from tests.support.facts import InMemoryFacts
from tests.support.facts import Store as FactStore
from tests.support.jobs import InMemoryApplications, InMemoryJobs, Store
from tests.support.profile import InMemoryProfiles


@dataclass
class AutoRun:
    """`locked` — прогін уже йде в іншому процесі; `failing` — користувачі, чия транзакція падає на
    збереженні (як збій бази)."""

    locked: bool = False
    failing: set[UserId] = field(default_factory=set)


class InMemoryTriage:
    def __init__(self, store: Store, run: AutoRun | None = None) -> None:
        self._s = store
        self._run = AutoRun() if run is None else run

    def _closed(self, owner: UserId, number: int) -> bool:
        application = self._s.applications.get((owner, number))
        return application is not None and application.status in CLOSED_STATUSES

    def _open_to_agent(self, owner: UserId, number: int) -> bool:
        """Без тріажу або з тріажем `rules` і вердиктом maybe: решту агент не бачить."""
        key = (owner, number)
        if key not in self._s.triage:
            return True
        return (
            key in self._s.rules_hashes
            and self._s.triage[key].verdict is TriageVerdict.MAYBE
        )

    def _untriaged(self, user_id: UserId) -> list[Job]:
        found = [
            job
            for (owner, number), job in self._s.jobs.items()
            if owner == user_id
            and not job.dismissed
            and not job.needs_text
            and self._open_to_agent(owner, number)
            and (owner, number) not in self._s.analyses
            and not self._closed(owner, number)
        ]
        return sorted(found, key=lambda job: (-job.created_at.timestamp(), -job.number))

    async def candidates(self, user_id: UserId, limit: int) -> list[Job]:
        return self._untriaged(user_id)[:limit]

    async def pending(self, user_id: UserId) -> int:
        return len(self._untriaged(user_id))

    async def save(
        self,
        user_id: UserId,
        items: Sequence[tuple[TriageId, JobId, TriageEntry]],
        now: datetime,
    ) -> None:
        for _, _, entry in items:
            self._put(user_id, entry, now, TriageSource.AGENT)
            self._s.rules_hashes.pop((user_id, entry.job_number), None)

    def _put(
        self,
        user_id: UserId,
        entry: TriageEntry,
        now: datetime,
        source: TriageSource,
    ) -> None:
        self._s.triage[(user_id, entry.job_number)] = Triage(
            job_number=entry.job_number,
            score=entry.score,
            verdict=entry.verdict,
            reason=entry.reason,
            triaged_at=now,
            source=source,
        )

    async def lock(self) -> bool:
        return not self._run.locked

    def _wanted(self, user_id: UserId) -> list[Job]:
        """Правило кандидата без умови про тріаж."""
        return [
            job
            for (owner, number), job in self._s.jobs.items()
            if owner == user_id
            and not job.dismissed
            and not job.needs_text
            and (owner, number) not in self._s.analyses
            and not self._closed(owner, number)
        ]

    async def users_with_work(self) -> list[UserId]:
        users = {
            owner
            for owner, _ in self._s.jobs
            for job in self._wanted(owner)
            if (owner, job.number) not in self._s.triage
            or (owner, job.number) in self._s.rules_hashes
        }
        return sorted(users, key=lambda user: user.value)

    async def users_with_jobs(self) -> list[UserId]:
        users = {
            owner for (owner, _), job in self._s.jobs.items() if not job.needs_text
        }
        return sorted(users, key=lambda user: user.value)

    async def auto_candidates(
        self, user_id: UserId, context: str, limit: int
    ) -> list[Job]:
        found = []
        for job in self._wanted(user_id):
            key = (user_id, job.number)
            if key not in self._s.triage or (
                key in self._s.rules_hashes
                and self._s.rules_hashes[key] != inputs_hash(context, job)
            ):
                found.append(job)
        found.sort(key=lambda job: (-job.created_at.timestamp(), -job.number))
        return found[:limit]

    async def save_auto(
        self,
        user_id: UserId,
        items: Sequence[tuple[TriageId, JobId, TriageEntry, str]],
        now: datetime,
    ) -> None:
        if user_id in self._run.failing:
            raise RuntimeError("Збій бази")
        for _, _, entry, digest in items:
            key = (user_id, entry.job_number)
            if key in self._s.triage and key not in self._s.rules_hashes:
                continue
            self._put(user_id, entry, now, TriageSource.RULES)
            self._s.rules_hashes[key] = digest

    async def analysed_scores(self, user_id: UserId) -> list[tuple[Job, int]]:
        return [
            (job, self._s.analyses[(owner, number)].analysis.score)
            for (owner, number), job in sorted(
                self._s.jobs.items(), key=lambda i: i[0][1]
            )
            if owner == user_id
            and not job.needs_text
            and (owner, number) in self._s.analyses
        ]


class InMemoryTriageUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(
        self,
        store: Store,
        profiles: dict[UserId, Profile],
        inputs_changed: dict[UserId, datetime] | None = None,
        facts: FactStore | None = None,
    ) -> None:
        self._store = store
        self._profiles = profiles
        self._inputs_changed = {} if inputs_changed is None else inputs_changed
        self._facts = FactStore.empty() if facts is None else facts
        self._staged: Store | None = None

    def _open(self) -> Store:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged

    @property
    def jobs(self) -> InMemoryJobs:
        return InMemoryJobs(self._open())

    @property
    def triage(self) -> InMemoryTriage:
        return InMemoryTriage(self._open())

    @property
    def analyses(self) -> InMemoryAnalyses:
        return InMemoryAnalyses(self._open())

    @property
    def applications(self) -> InMemoryApplications:
        return InMemoryApplications(self._open())

    @property
    def profiles(self) -> InMemoryProfiles:
        return InMemoryProfiles(self._profiles, {}, self._inputs_changed)

    @property
    def facts(self) -> InMemoryFacts:
        return InMemoryFacts(self._facts)

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
        staged = self._open()
        self._store.jobs, self._store.counters = staged.jobs, staged.counters
        self._store.hashes, self._store.linkedin = staged.hashes, staged.linkedin
        self._store.triage = staged.triage
        self._store.rules_hashes = staged.rules_hashes
        self._store.analyses = staged.analyses


class InMemoryAutoTriageUnitOfWork:
    """Для тріажу за правилами: зміни тріажу видно лише після `commit()`."""

    def __init__(
        self,
        store: Store,
        profiles: dict[UserId, Profile],
        facts: FactStore,
        run: AutoRun,
    ) -> None:
        self._store = store
        self._profiles = profiles
        self._facts = facts
        self._run = run
        self._staged: Store | None = None

    def _open(self) -> Store:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged

    @property
    def triage(self) -> InMemoryTriage:
        return InMemoryTriage(self._open(), self._run)

    @property
    def profiles(self) -> InMemoryProfiles:
        return InMemoryProfiles(self._profiles, {}, {})

    @property
    def facts(self) -> InMemoryFacts:
        return InMemoryFacts(self._facts)

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
        staged = self._open()
        self._store.triage = staged.triage
        self._store.rules_hashes = staged.rules_hashes
