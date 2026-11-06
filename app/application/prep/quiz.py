"""Use cases квізу: Claude пише питання до теми й веде квіз у чаті, сервер зберігає питання,
історію відповідей і розклад повторень (Leitner, «сьогодні» — за Мадридом).

Тема й питання скрізь — за номером у межах користувача; чуже й неіснуюче не відрізняються.
"""

from collections.abc import Callable, Sequence
from datetime import date

from application.contracts.actor import Actor
from application.contracts.quiz import (
    AnswerInput,
    DueQuestionData,
    DueQuizData,
    QuestionData,
    QuestionInput,
    QuestionsBriefData,
    QuizCountData,
    SavedQuestionsData,
)
from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.prompts import PromptKey, Prompts
from application.ports.quiz import QuizUnitOfWork
from application.prep.use_cases import detail_data
from domain.identity.ids import UserId
from domain.prep.ids import AnswerId, QuestionId
from domain.prep.quiz import (
    DEFAULT_DUE_LIMIT,
    MAX_QUESTIONS_PER_SAVE,
    Answer,
    NewQuestion,
    PrepQuestion,
    check_due_limit,
    due,
    first_schedule,
    next_schedule,
    quiz_counts,
)
from domain.prep.topic import PrepTopic
from domain.shared.errors import InvalidValue, NotFound
from domain.shared.local_time import local_today


class QuizUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], QuizUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        prompts: Prompts,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids
        self._prompts = prompts

    async def prepare_questions(
        self, actor: Actor, topic_number: int
    ) -> QuestionsBriefData:
        """Тема з планом і нотатками, її наявні питання і правила питань. `NotFound` — теми
        нема чи вона чужа."""
        async with self._unit_of_work() as uow:
            topic = await _topic(uow, actor.user_id, topic_number)
            questions = await uow.prep_questions.all(actor.user_id, topic_number)
        return QuestionsBriefData(
            detail=detail_data(topic),
            questions=tuple(question_data(question) for question in questions),
            rules=self._prompts.get(PromptKey.PREP_QUESTION_RULES),
        )

    async def save_questions(
        self, actor: Actor, topic_number: int, items: Sequence[QuestionInput]
    ) -> SavedQuestionsData:
        """Додає питання до теми на повторення сьогодні, дублі пропускає. `InvalidValue`
        («Питання N: …») / `NotFound` — нічого не збережено."""
        if not items:
            raise InvalidValue("questions", "Список питань порожній.")
        if len(items) > MAX_QUESTIONS_PER_SAVE:
            raise InvalidValue(
                "questions", f"За раз — до {MAX_QUESTIONS_PER_SAVE} питань."
            )
        questions = [_parse(position, item) for position, item in enumerate(items, 1)]
        now = self._clock.now()
        schedule = first_schedule(local_today(now))
        async with self._unit_of_work() as uow:
            await _topic(uow, actor.user_id, topic_number)
            added: list[int] = []
            skipped: list[str] = []
            for question in questions:
                number = await uow.prep_questions.add(
                    actor.user_id,
                    QuestionId(self._ids.new()),
                    topic_number,
                    question,
                    schedule,
                    now,
                )
                if number is None:
                    skipped.append(question.question)
                else:
                    added.append(number)
            saved = {
                question.number: question
                for question in await uow.prep_questions.all(
                    actor.user_id, topic_number
                )
            }
            await uow.commit()
        return SavedQuestionsData(
            added=tuple(question_data(saved[number]) for number in added),
            skipped=tuple(skipped),
        )

    async def due_questions(
        self,
        actor: Actor,
        *,
        limit: int = DEFAULT_DUE_LIMIT,
        topic_number: int | None = None,
    ) -> DueQuizData:
        """Питання, яким настав час (усі теми чи одна), і правила квізу. `InvalidValue` —
        limit поза межами; `NotFound` — теми нема чи вона чужа."""
        check_due_limit(limit)
        today = local_today(self._clock.now())
        async with self._unit_of_work() as uow:
            if topic_number is not None:
                await _topic(uow, actor.user_id, topic_number)
            questions = await uow.prep_questions.all(actor.user_id, topic_number)
        found = due(questions, today)
        return DueQuizData(
            questions=tuple(
                DueQuestionData(
                    question=question_data(question),
                    answer_points=question.answer_points,
                )
                for question in found[:limit]
            ),
            total=len(found),
            rules=self._prompts.get(PromptKey.PREP_QUIZ_RULES),
        )

    async def record_answer(
        self, actor: Actor, question_number: int, data: AnswerInput
    ) -> QuestionData:
        """Зберігає спробу в історії й переносить питання в нову коробку. Повертає питання з
        новим розкладом. `InvalidValue` / `NotFound` — нічого не змінено."""
        answer = Answer.parse(
            grade=data.grade, answer=data.answer, feedback=data.feedback
        )
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            question = await uow.prep_questions.get(actor.user_id, question_number)
            if question is None:
                raise NotFound(f"Питання {question_number} не знайдено.")
            schedule = next_schedule(question.box, answer.grade, local_today(now))
            await uow.prep_questions.record(
                actor.user_id,
                AnswerId(self._ids.new()),
                question_number,
                answer,
                schedule,
                now,
            )
            await uow.commit()
        return question_data(question, box=schedule.box, due_on=schedule.due_on)

    async def count_questions(self, actor: Actor) -> dict[int, QuizCountData]:
        """Питань у кожній темі користувача (за номером теми) і скільки з них на повторенні
        сьогодні; теми без питань відсутні."""
        today = local_today(self._clock.now())
        async with self._unit_of_work() as uow:
            questions = await uow.prep_questions.all(actor.user_id)
        return {
            topic: QuizCountData(total=count.total, due=count.due)
            for topic, count in quiz_counts(questions, today).items()
        }


async def _topic(uow: QuizUnitOfWork, user: UserId, topic_number: int) -> PrepTopic:
    topic = await uow.prep_topics.get(user, topic_number)
    if topic is None:
        raise NotFound(f"Тему {topic_number} не знайдено.")
    return topic


def _parse(position: int, item: QuestionInput) -> NewQuestion:
    try:
        return NewQuestion.parse(
            question=item.question, answer_points=item.answer_points
        )
    except InvalidValue as error:
        raise InvalidValue(
            error.field, f"Питання {position}: {error.message}"
        ) from error


def question_data(
    question: PrepQuestion, *, box: int | None = None, due_on: date | None = None
) -> QuestionData:
    return QuestionData(
        question_number=question.number,
        topic_number=question.topic_number,
        topic_title=question.topic_title,
        question=question.question,
        box=question.box if box is None else box,
        due_on=question.due_on if due_on is None else due_on,
    )
