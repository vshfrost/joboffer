"""Порти пакета до інтерв'ю: репозиторій версій і unit of work, що його відкриває.

Вакансія — за `JobId`, який use case бере з власної вакансії користувача, тож чужі пакети
недосяжні; версія — за номером у межах користувача (`number`).
"""

from datetime import datetime
from typing import Protocol

from application.ports.facts import FactRepository
from application.ports.prep import PrepUnitOfWork
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.prep.ids import KitId
from domain.prep.kit import InterviewKit, KitVersion


class InterviewKitRepository(Protocol):
    async def add(
        self,
        user_id: UserId,
        kit_id: KitId,
        job_id: JobId,
        kit: InterviewKit,
        now: datetime,
    ) -> KitVersion:
        """Нова версія пакета вакансії: наступна після останньої (з 1) і наступний номер
        користувача. Паралельні збереження одного користувача йдуть по черзі."""
        ...

    async def latest(self, user_id: UserId, job_id: JobId) -> KitVersion | None:
        """Остання версія пакета вакансії; пакета нема — `None`."""
        ...


class InterviewKitUnitOfWork(PrepUnitOfWork, Protocol):
    @property
    def facts(self) -> FactRepository: ...

    @property
    def interview_kits(self) -> InterviewKitRepository: ...
