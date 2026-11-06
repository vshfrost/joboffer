"""Порти контексту analysis: репозиторій аналізів і unit of work, що його відкриває.

Аналіз скрізь — за вакансією; чужа й неіснуюча не відрізняються.
"""

from datetime import datetime
from typing import Protocol

from application.ports.facts import FactRepository
from application.ports.jobs import JobRepository
from application.ports.profile import ProfileRepository
from application.ports.unit_of_work import UnitOfWork
from domain.analysis.analysis import Analysis, JobAnalysis
from domain.analysis.gap_answer import GapAnswer
from domain.analysis.ids import AnalysisId, GapAnswerId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId


class AnalysisRepository(Protocol):
    async def get(self, user_id: UserId, job_id: JobId) -> Analysis | None:
        """Аналіз вакансії або None, якщо її ще не аналізовано."""
        ...

    async def save(  # noqa: PLR0913, PLR0917
        self,
        user_id: UserId,
        analysis_id: AnalysisId,
        job_id: JobId,
        analysis: JobAnalysis,
        flags: tuple[str, ...],
        now: datetime,
    ) -> None:
        """Замінює попередній аналіз вакансії (його id лишається першим)."""
        ...


class GapAnswerRepository(Protocol):
    async def for_job(self, user_id: UserId, job_id: JobId) -> list[GapAnswer]:
        """Усі відповіді на прогалини вакансії в порядку відповіді."""
        ...

    async def save(
        self,
        user_id: UserId,
        answer_id: GapAnswerId,
        job_id: JobId,
        answer: GapAnswer,
    ) -> None:
        """Одна відповідь на текст прогалини (без регістру й зайвих пробілів): повторна замінює
        попередню разом із її фактами."""
        ...


class AnalysisUnitOfWork(UnitOfWork, Protocol):
    @property
    def jobs(self) -> JobRepository: ...

    @property
    def analyses(self) -> AnalysisRepository: ...

    @property
    def gap_answers(self) -> GapAnswerRepository: ...

    @property
    def facts(self) -> FactRepository: ...

    @property
    def profiles(self) -> ProfileRepository: ...
