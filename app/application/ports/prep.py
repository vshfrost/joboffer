"""Порти контексту prep: репозиторій тем підготовки й unit of work, що його відкриває.

Тема — за номером у межах користувача (`number`) і спільна для всіх його вакансій (slug);
вакансія — за номером. Чужа й неіснуюча не відрізняються.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from application.ports.analysis import AnalysisRepository
from application.ports.documents import DocumentRepository
from application.ports.facts import FactRepository
from application.ports.jobs import JobRepository
from application.ports.unit_of_work import UnitOfWork
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.prep.ids import StepId, TopicId
from domain.prep.plan import NewStep
from domain.prep.topic import NewTopic, PrepTopic


class PrepTopicRepository(Protocol):
    async def save(  # noqa: PLR0913, PLR0917
        self,
        user_id: UserId,
        topic_id: TopicId,
        job_id: JobId,
        topic: NewTopic,
        gap: str,
        now: datetime,
    ) -> int:
        """Тема з таким slug уже є → її поля замінено (`topic_id` не потрібен), інакше створено
        з наступним номером користувача. Вакансію прив'язано до теми: повтор для тієї самої
        вакансії замінює `gap`, другої прив'язки нема. Повертає номер теми."""
        ...

    async def all(self, user_id: UserId) -> list[PrepTopic]:
        """Усі теми користувача за номером, кожна з прив'язаними вакансіями (за номером вакансії)
        і поточним скором їхнього аналізу; сховані й подані вакансії теж рахуються. Кожна
        тема — зі своїми кроками за позицією і позначкою «готово»."""
        ...

    async def get(self, user_id: UserId, number: int) -> PrepTopic | None:
        """Тема користувача за номером, повна (як у `all`); чужа й неіснуюча — `None`."""
        ...

    async def replace_pending_steps(
        self,
        user_id: UserId,
        topic_number: int,
        steps: Sequence[tuple[StepId, NewStep]],
    ) -> None:
        """Видаляє невиконані кроки теми, нові додає після останнього кроку, що лишився
        (позиція — наступна за найбільшою), кожному — наступний номер користувача (номери
        видалених не повторюються). Виконані кроки не змінюються."""
        ...

    async def complete_step(
        self, user_id: UserId, step_number: int, note: str, now: datetime
    ) -> int | None:
        """Позначає крок виконаним: перша дата лишається, непорожня нотатка замінює стару.
        Повертає номер теми кроку; чужий і неіснуючий крок — `None`, нічого не змінено."""
        ...

    async def set_ready(
        self, user_id: UserId, topic_number: int, *, ready: bool, now: datetime
    ) -> None:
        """`ready` — ставить позначку «готово» (перша дата лишається), інакше знімає її."""
        ...


class PrepUnitOfWork(UnitOfWork, Protocol):
    @property
    def jobs(self) -> JobRepository: ...

    @property
    def analyses(self) -> AnalysisRepository: ...

    @property
    def prep_topics(self) -> PrepTopicRepository: ...

    @property
    def documents(self) -> DocumentRepository: ...

    @property
    def facts(self) -> FactRepository: ...
