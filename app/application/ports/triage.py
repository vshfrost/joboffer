"""Порти контексту triage: репозиторій тріажу й unit of work, що його відкриває.

Тріаж скрізь — за номером вакансії в межах користувача; чужа й неіснуюча не відрізняються.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from application.ports.analysis import AnalysisRepository
from application.ports.applications import ApplicationRepository
from application.ports.facts import FactRepository
from application.ports.jobs import JobRepository
from application.ports.profile import ProfileRepository
from application.ports.unit_of_work import UnitOfWork
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import Job
from domain.triage.ids import TriageId
from domain.triage.triage import TriageEntry


class TriageRepository(Protocol):
    async def candidates(self, user_id: UserId, limit: int) -> list[Job]:
        """Кандидати агента: не сховані вакансії з текстом без аналізу й відмови (подача rejected / withdrawn),
        без тріажу або з тріажем `rules` і вердиктом maybe; новіші першими."""
        ...

    async def pending(self, user_id: UserId) -> int:
        """Скільки вакансій чекає на агента (ті самі, що в `candidates`, без ліміту)."""
        ...

    async def save(
        self,
        user_id: UserId,
        items: Sequence[tuple[TriageId, JobId, TriageEntry]],
        now: datetime,
    ) -> None:
        """Зберігає тріаж агента (`source = agent`); повторний тріаж вакансії перезаписує попередній
        (id лишається першим), у т.ч. рядок `rules`."""
        ...

    async def lock(self) -> bool:
        """Бере лок прогону до кінця транзакції; `False` — прогін уже йде в іншому процесі."""
        ...

    async def users_with_work(self) -> list[UserId]:
        """Користувачі з вакансіями, що задовольняють правило кандидата (з текстом, без аналізу, не
        сховані, без закритої подачі) і ще без тріажу або з тріажем `rules`; за id."""
        ...

    async def users_with_jobs(self) -> list[UserId]:
        """Користувачі, що мають вакансію з текстом; за id."""
        ...

    async def auto_candidates(
        self, user_id: UserId, context: str, limit: int
    ) -> list[Job]:
        """Вакансії за правилом кандидата без тріажу або з тріажем `rules`, чий відбиток не збігається
        з `inputs_hash(context, вакансія)`; тріаж `agent` — ніколи. Новіші першими."""
        ...

    async def save_auto(
        self,
        user_id: UserId,
        items: Sequence[tuple[TriageId, JobId, TriageEntry, str]],
        now: datetime,
    ) -> None:
        """Зберігає тріаж `rules` з відбитком вхідних даних (останній елемент). Новий рядок або
        перерахунок `rules` (id лишається першим); рядок `agent` ніколи не перезаписується."""
        ...

    async def analysed_scores(self, user_id: UserId) -> list[tuple[Job, int]]:
        """Вакансії з текстом і скором їхнього повного аналізу; за номером."""
        ...


class AutoTriageUnitOfWork(UnitOfWork, Protocol):
    @property
    def triage(self) -> TriageRepository: ...

    @property
    def profiles(self) -> ProfileRepository: ...

    @property
    def facts(self) -> FactRepository: ...


class TriageUnitOfWork(UnitOfWork, Protocol):
    @property
    def jobs(self) -> JobRepository: ...

    @property
    def triage(self) -> TriageRepository: ...

    @property
    def analyses(self) -> AnalysisRepository: ...

    @property
    def applications(self) -> ApplicationRepository: ...

    @property
    def profiles(self) -> ProfileRepository: ...

    @property
    def facts(self) -> FactRepository: ...
