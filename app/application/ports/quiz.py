"""Порти квізу: репозиторій питань з історією відповідей і unit of work, що його відкриває.

Питання й тема — за номером у межах користувача; чуже й неіснуюче не відрізняються.
"""

from datetime import datetime
from typing import Protocol

from application.ports.prep import PrepUnitOfWork
from domain.identity.ids import UserId
from domain.prep.ids import AnswerId, QuestionId
from domain.prep.quiz import Answer, NewQuestion, PastAnswer, PrepQuestion, Schedule


class PrepQuestionRepository(Protocol):
    async def all(
        self, user_id: UserId, topic_number: int | None = None
    ) -> list[PrepQuestion]:
        """Питання користувача (лише теми `topic_number`, якщо задано) за номером, кожне з
        назвою своєї теми."""
        ...

    async def get(self, user_id: UserId, number: int) -> PrepQuestion | None:
        """Питання користувача за номером; чуже й неіснуюче — `None`."""
        ...

    async def add(  # noqa: PLR0913, PLR0917
        self,
        user_id: UserId,
        question_id: QuestionId,
        topic_number: int,
        question: NewQuestion,
        schedule: Schedule,
        now: datetime,
    ) -> int | None:
        """Нове питання теми (вона вже перевірена як своя) з наступним номером користувача.
        Таке саме питання в темі вже є (без урахування пробілів і регістру) → `None`, номер не
        витрачено."""
        ...

    async def record(  # noqa: PLR0913, PLR0917
        self,
        user_id: UserId,
        answer_id: AnswerId,
        number: int,
        answer: Answer,
        schedule: Schedule,
        now: datetime,
    ) -> None:
        """Додає спробу в історію питання (воно вже перевірене як своє) і переносить його в
        коробку й на день з `schedule`."""
        ...

    async def answers(self, user_id: UserId, number: int) -> list[PastAnswer]:
        """Історія спроб питання від найстарішої; чуже й неіснуюче питання — порожня."""
        ...


class QuizUnitOfWork(PrepUnitOfWork, Protocol):
    @property
    def prep_questions(self) -> PrepQuestionRepository: ...
