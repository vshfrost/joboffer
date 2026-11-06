"""In-memory адаптер квізу для core-тестів: та сама семантика, що в Postgres (номери на
користувача, дубль у темі, історія спроб, commit).

Ділить `PrepStore` з фейком тем: питання бачать назву своєї теми.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from types import TracebackType
from typing import Self

from domain.identity.ids import UserId
from domain.prep.ids import AnswerId, QuestionId
from domain.prep.quiz import Answer, NewQuestion, PastAnswer, PrepQuestion, Schedule
from tests.support.jobs import Store
from tests.support.prep import InMemoryPrepUnitOfWork, PrepStore


@dataclass(frozen=True, slots=True)
class StoredQuestion:
    id: QuestionId
    topic_number: int
    question: NewQuestion
    schedule: Schedule
    created_at: datetime


@dataclass
class QuizStore:
    questions: dict[tuple[UserId, int], StoredQuestion]
    # Останній виданий номер питання користувача: дубль чи скасована транзакція номера не витрачають.
    counters: dict[UserId, int]
    answers: dict[tuple[UserId, int], list[PastAnswer]] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> Self:
        return cls({}, {})

    def copy(self) -> Self:
        return type(self)(
            dict(self.questions),
            dict(self.counters),
            {key: list(history) for key, history in self.answers.items()},
        )


class InMemoryPrepQuestions:
    def __init__(self, quiz: QuizStore, prep: PrepStore) -> None:
        self._q = quiz
        self._p = prep

    def _view(
        self, user_id: UserId, number: int, stored: StoredQuestion
    ) -> PrepQuestion:
        topic = self._p.topics[(user_id, stored.topic_number)]
        return PrepQuestion(
            id=stored.id,
            number=number,
            topic_number=stored.topic_number,
            topic_title=topic.title,
            question=stored.question.question,
            answer_points=stored.question.answer_points,
            box=stored.schedule.box,
            due_on=stored.schedule.due_on,
            created_at=stored.created_at,
        )

    async def all(
        self, user_id: UserId, topic_number: int | None = None
    ) -> list[PrepQuestion]:
        return [
            self._view(owner, number, stored)
            for (owner, number), stored in sorted(
                self._q.questions.items(), key=lambda item: item[0][1]
            )
            if owner == user_id
            and (topic_number is None or stored.topic_number == topic_number)
        ]

    async def get(self, user_id: UserId, number: int) -> PrepQuestion | None:
        stored = self._q.questions.get((user_id, number))
        return None if stored is None else self._view(user_id, number, stored)

    async def add(
        self,
        user_id: UserId,
        question_id: QuestionId,
        topic_number: int,
        question: NewQuestion,
        schedule: Schedule,
        now: datetime,
    ) -> int | None:
        for (owner, _), stored in self._q.questions.items():
            if (
                owner == user_id
                and stored.topic_number == topic_number
                and stored.question.fingerprint == question.fingerprint
            ):
                return None
        number = self._q.counters.get(user_id, 0) + 1
        self._q.counters[user_id] = number
        self._q.questions[(user_id, number)] = StoredQuestion(
            question_id, topic_number, question, schedule, now
        )
        return number

    async def record(
        self,
        user_id: UserId,
        answer_id: AnswerId,
        number: int,
        answer: Answer,
        schedule: Schedule,
        now: datetime,
    ) -> None:
        key = (user_id, number)
        self._q.questions[key] = replace(self._q.questions[key], schedule=schedule)
        self._q.answers.setdefault(key, []).append(
            PastAnswer(answer.grade, answer.answer, answer.feedback, schedule.box, now)
        )

    async def answers(self, user_id: UserId, number: int) -> list[PastAnswer]:
        return list(self._q.answers.get((user_id, number), []))


class InMemoryQuizUnitOfWork(InMemoryPrepUnitOfWork):
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(self, store: Store, prep: PrepStore, quiz: QuizStore) -> None:
        super().__init__(store, prep)
        self._quiz = quiz
        self._staged_quiz: QuizStore | None = None

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self._staged_quiz = self._quiz.copy()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged_quiz = None
        await super().__aexit__(exc_type, exc, traceback)

    @property
    def prep_questions(self) -> InMemoryPrepQuestions:
        if self._staged_quiz is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemoryPrepQuestions(self._staged_quiz, self._open()[1])

    async def commit(self) -> None:
        await super().commit()
        if self._staged_quiz is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        self._quiz.questions = self._staged_quiz.questions
        self._quiz.counters = self._staged_quiz.counters
        self._quiz.answers = self._staged_quiz.answers
