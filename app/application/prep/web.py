"""Підготовка для вебу: реєстр тем, сторінка теми, «виконано» з нотаткою, «готово» і підготовка до
вакансії. Теми, плани й питання створює лише Claude через MCP — тут їх читають і ведуть прогрес.

Тема, крок і вакансія скрізь — за номером у межах користувача; чужа й неіснуюча не відрізняються.
"""

from collections.abc import Callable, Mapping

from application.contracts.actor import Actor
from application.contracts.prep_web import (
    JobPrepData,
    TopicBoardData,
    TopicPageData,
    TopicRowData,
)
from application.contracts.quiz import QuizCountData
from application.ports.clock import Clock
from application.ports.quiz import QuizUnitOfWork
from application.prep.use_cases import PrepUseCases, detail_data, topic_data
from domain.identity.ids import UserId
from domain.prep.quiz import QuizCount, quiz_counts
from domain.prep.topic import PrepTopic, by_priority, readiness
from domain.shared.errors import NotFound
from domain.shared.local_time import local_today


class PrepWebUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], QuizUnitOfWork],
        clock: Clock,
        prep: PrepUseCases,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._prep = prep

    async def topics(self, actor: Actor) -> TopicBoardData:
        """Усі теми користувача за пріоритетом і загальні лічильники квізу."""
        today = local_today(self._clock.now())
        async with self._unit_of_work() as uow:
            topics = by_priority(await uow.prep_topics.all(actor.user_id))
            questions = await uow.prep_questions.all(actor.user_id)
        counts = quiz_counts(questions, today)
        return TopicBoardData(
            topics=tuple(_row(topic, counts) for topic in topics),
            quiz=QuizCountData(
                total=sum(count.total for count in counts.values()),
                due=sum(count.due for count in counts.values()),
            ),
        )

    async def topic(self, actor: Actor, topic_number: int) -> TopicPageData:
        """Тема з кроками й вакансіями. `NotFound` — теми нема чи вона чужа."""
        today = local_today(self._clock.now())
        async with self._unit_of_work() as uow:
            topic = await _topic(uow, actor.user_id, topic_number)
            questions = await uow.prep_questions.all(actor.user_id, topic_number)
        counts = quiz_counts(questions, today)
        return TopicPageData(
            detail=detail_data(topic),
            percent=topic.percent,
            quiz=_quiz(counts, topic.number),
        )

    async def complete_step(
        self, actor: Actor, step_number: int, note: str = ""
    ) -> TopicPageData:
        """Крок виконано (повтор лишає першу дату й замінює нотатку, якщо вона є). Повертає тему
        кроку. `InvalidValue` («note») / `NotFound` — нічого не змінено."""
        done = await self._prep.complete_step(actor, step_number, note)
        return await self.topic(actor, done.topic.topic_number)

    async def set_topic_ready(
        self, actor: Actor, topic_number: int, *, ready: bool
    ) -> TopicPageData:
        """Тему готовою позначає користувач; `ready=False` повертає статус із кроків. `NotFound` —
        теми нема чи вона чужа."""
        marked = await self._prep.set_topic_ready(actor, topic_number, ready=ready)
        return await self.topic(actor, marked.topic.topic_number)

    async def job_prep(self, actor: Actor, job_number: int) -> JobPrepData:
        """Теми вакансії за пріоритетом і готовність до неї (середнє по темах; `None` — тем нема).
        `NotFound` — вакансії нема чи вона чужа."""
        today = local_today(self._clock.now())
        async with self._unit_of_work() as uow:
            if await uow.jobs.get(actor.user_id, job_number) is None:
                raise NotFound(f"Вакансію {job_number} не знайдено.")
            every = await uow.prep_topics.all(actor.user_id)
            questions = await uow.prep_questions.all(actor.user_id)
        topics = by_priority(
            topic
            for topic in every
            if any(job.job_number == job_number for job in topic.jobs)
        )
        counts = quiz_counts(questions, today)
        return JobPrepData(
            readiness=readiness(topics),
            topics=tuple(_row(topic, counts) for topic in topics),
        )


async def _topic(uow: QuizUnitOfWork, user: UserId, topic_number: int) -> PrepTopic:
    topic = await uow.prep_topics.get(user, topic_number)
    if topic is None:
        raise NotFound(f"Тему {topic_number} не знайдено.")
    return topic


def _quiz(counts: Mapping[int, QuizCount], topic_number: int) -> QuizCountData:
    count = counts.get(topic_number, QuizCount())
    return QuizCountData(total=count.total, due=count.due)


def _row(topic: PrepTopic, counts: Mapping[int, QuizCount]) -> TopicRowData:
    return TopicRowData(
        topic=topic_data(topic),
        percent=topic.percent,
        quiz=_quiz(counts, topic.number),
    )
