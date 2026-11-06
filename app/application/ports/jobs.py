"""Порти контексту jobs: репозиторій вакансій і unit of work, що його відкриває.

Усюди вакансія — за номером у межах користувача (`job_number`); чужа й неіснуюча не відрізняються.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from application.ports.applications import ApplicationRepository
from application.ports.unit_of_work import UnitOfWork
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import Job, JobSummary, NewJob
from domain.jobs.search import JobSearch, JobTabCounts
from domain.sources.dedup import RecentJob
from domain.triage.triage import Triage


class JobRepository(Protocol):
    async def lock_additions(self, user_id: UserId) -> None:
        """До кінця транзакції додавання вакансій цього користувача йдуть по черзі:
        пошук дубля й вставка не бʼються з паралельним додаванням того самого."""
        ...

    async def find_duplicate(self, user_id: UserId, job: NewJob) -> int | None:
        """Номер наявної вакансії з тим самим текстом, URL чи LinkedIn id (порожнє не дублює)."""
        ...

    async def find_linkedin(self, user_id: UserId, linkedin_id: str) -> int | None:
        """Номер вакансії з цим LinkedIn id (або з його канонічним URL)."""
        ...

    async def add(
        self,
        user_id: UserId,
        job_id: JobId,
        job: NewJob,
        now: datetime,
        number: int | None = None,
    ) -> int:
        """Додає вакансію; повертає її номер. `number` не задано — наступний номер користувача
        (з 1); задано явно (перенос з v1) — лічильник не відстає від нього."""
        ...

    async def recent(self, user_id: UserId, since: datetime) -> list[RecentJob]:
        """Вакансії, додані не раніше `since` (сховані теж): для дедупу «компанія + посада»."""
        ...

    async def complete_text(self, user_id: UserId, number: int, text: str) -> None:
        """Дописує опис у вакансію без тексту; з текстом не чіпає."""
        ...

    async def get(self, user_id: UserId, number: int) -> Job | None: ...

    async def mark_opened(self, user_id: UserId, number: int, now: datetime) -> None:
        """Ставить час першого відкриття; уже відкриту не чіпає."""
        ...

    async def search(self, user_id: UserId, search: JobSearch) -> list[JobSummary]:
        """Новіші першими, «потрібен текст» наприкінці."""
        ...

    async def tab_counts(self, user_id: UserId) -> JobTabCounts:
        """Лічильники табів вебу користувача: кількість «у процесі», чи є нерозібраний лист до
        активної подачі, чи є не схована вакансія без тексту. Відмови не рахуються."""
        ...

    async def get_triage(self, user_id: UserId, number: int) -> Triage | None:
        """Тріаж вакансії для деталей; None — її ще не тріажовано."""
        ...

    async def sources(self, user_id: UserId) -> list[str]:
        """Різні джерела вакансій користувача за абеткою."""
        ...

    async def source_jobs(self, user_id: UserId) -> list[Job]:
        """Вакансії з джерел (`ats:` / `rss:`) з текстом: не сховані, без повного аналізу й
        без подачі. За номером."""
        ...

    async def dismiss(
        self, user_id: UserId, numbers: Sequence[int], reason: str, now: datetime
    ) -> None:
        """Ховає не сховані; сховану не чіпає (причина лишається перша)."""
        ...

    async def restore(self, user_id: UserId, number: int) -> None:
        """Повертає сховану в список; не сховану не змінює."""
        ...


class JobUnitOfWork(UnitOfWork, Protocol):
    @property
    def jobs(self) -> JobRepository: ...

    @property
    def applications(self) -> ApplicationRepository: ...
