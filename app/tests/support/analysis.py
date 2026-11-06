"""In-memory адаптер analysis для core-тестів: та сама семантика, що в Postgres (заміна, commit).

Ділить `Store` із фейком вакансій: аналіз бачить ті самі вакансії, що й список.
"""

from datetime import datetime
from types import TracebackType
from typing import Self

from domain.analysis.analysis import Analysis, JobAnalysis
from domain.analysis.gap_answer import GapAnswer
from domain.analysis.ids import AnalysisId, GapAnswerId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.profile.profile import Profile
from domain.shared.fingerprint import text_fingerprint
from tests.support.facts import InMemoryFacts
from tests.support.facts import Store as FactStore
from tests.support.jobs import InMemoryJobs, Store
from tests.support.profile import InMemoryProfiles


class InMemoryAnalyses:
    def __init__(self, store: Store) -> None:
        self._s = store

    def _number(self, user_id: UserId, job_id: JobId) -> int | None:
        for (owner, number), job in self._s.jobs.items():
            if owner == user_id and job.id == job_id:
                return number
        return None

    async def get(self, user_id: UserId, job_id: JobId) -> Analysis | None:
        number = self._number(user_id, job_id)
        return None if number is None else self._s.analyses.get((user_id, number))

    async def save(
        self,
        user_id: UserId,
        analysis_id: AnalysisId,
        job_id: JobId,
        analysis: JobAnalysis,
        flags: tuple[str, ...],
        now: datetime,
    ) -> None:
        number = self._number(user_id, job_id)
        assert number is not None
        self._s.analyses[(user_id, number)] = Analysis(number, analysis, flags, now)


class InMemoryGapAnswers:
    def __init__(self, store: Store) -> None:
        self._s = store

    async def for_job(self, user_id: UserId, job_id: JobId) -> list[GapAnswer]:
        number = InMemoryAnalyses(self._s)._number(user_id, job_id)
        found = [
            answer
            for (owner, job, _), answer in self._s.gap_answers.items()
            if owner == user_id and job == number
        ]
        return sorted(found, key=lambda answer: answer.answered_at)

    async def save(
        self,
        user_id: UserId,
        answer_id: GapAnswerId,
        job_id: JobId,
        answer: GapAnswer,
    ) -> None:
        number = InMemoryAnalyses(self._s)._number(user_id, job_id)
        assert number is not None
        key = (user_id, number, text_fingerprint(answer.gap))
        self._s.gap_answers[key] = answer


class InMemoryAnalysisUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(
        self,
        store: Store,
        facts: FactStore,
        profiles: dict[UserId, Profile],
        inputs_changed: dict[UserId, datetime],
    ) -> None:
        self._store = store
        self._facts = facts
        self._profiles = profiles
        self._inputs_changed = inputs_changed
        self._staged: Store | None = None

    def _open(self) -> Store:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged

    @property
    def jobs(self) -> InMemoryJobs:
        return InMemoryJobs(self._open())

    @property
    def analyses(self) -> InMemoryAnalyses:
        return InMemoryAnalyses(self._open())

    @property
    def gap_answers(self) -> InMemoryGapAnswers:
        return InMemoryGapAnswers(self._open())

    @property
    def facts(self) -> InMemoryFacts:
        return InMemoryFacts(self._facts)

    @property
    def profiles(self) -> InMemoryProfiles:
        return InMemoryProfiles(self._profiles, {}, self._inputs_changed)

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
        self._store.analyses = self._open().analyses
        self._store.gap_answers = self._open().gap_answers
