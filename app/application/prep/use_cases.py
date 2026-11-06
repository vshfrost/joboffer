"""Use cases тем підготовки до інтерв'ю. MCP викликає саме їх — правила в одному місці.

Claude пропонує теми з прогалин проаналізованої вакансії, користувач погоджує, сервер валідує й
зберігає: нова тема або заміна полів наявної (той самий slug) плюс прив'язка вакансії з її
прогалиною. Далі Claude пише план теми (кроки learn → practice → check), веде користувача кроками й
позначає виконані; «готово» ставить лише користувач. Вакансія, тема й крок скрізь — за номером у
межах користувача; чужа й неіснуюча не відрізняються.
"""

from collections.abc import Callable, Sequence

from application.analysis.use_cases import analysis_data
from application.contracts.actor import Actor
from application.contracts.prep import (
    CvLineData,
    PlanBriefData,
    ResourceData,
    StepData,
    StepInput,
    TopicData,
    TopicDetailData,
    TopicInput,
    TopicJobData,
    TopicsBriefData,
)
from application.facts.use_cases import fact_data
from application.jobs.use_cases import job_data
from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.prep import PrepUnitOfWork
from application.ports.prompts import PromptKey, Prompts
from domain.analysis.analysis import Analysis
from domain.documents.document import Cv, DocumentKind
from domain.identity.ids import UserId
from domain.jobs.job import Job
from domain.prep.ids import StepId, TopicId
from domain.prep.plan import NewStep, PrepStep, check_plan, parse_note
from domain.prep.topic import (
    MAX_TOPICS_PER_SAVE,
    NewTopic,
    PrepTopic,
    by_priority,
    check_unique_slugs,
    parse_gap,
)
from domain.shared.errors import InvalidValue, NotFound


class PrepUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], PrepUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        prompts: Prompts,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids
        self._prompts = prompts

    async def prepare_prep_topics(
        self, actor: Actor, job_number: int
    ) -> TopicsBriefData:
        """Вакансія, її аналіз, усі теми користувача за пріоритетом, рядки останнього CV вакансії
        з їхніми фактами (CV нема — порожньо) і правила. `NotFound` — вакансії нема чи вона чужа;
        `InvalidValue` — вакансію ще не проаналізовано."""
        async with self._unit_of_work() as uow:
            job, analysis = await _analysed_job(uow, actor.user_id, job_number)
            topics = by_priority(await uow.prep_topics.all(actor.user_id))
            documents = await uow.documents.list_for_job(actor.user_id, job.id)
            facts = {fact.number: fact for fact in await uow.facts.all(actor.user_id)}
        cv = next(
            (
                document.content
                for document in documents
                if document.kind is DocumentKind.CV and isinstance(document.content, Cv)
            ),
            None,
        )
        return TopicsBriefData(
            job=job_data(job, None),
            analysis=analysis_data(analysis, None),
            topics=tuple(topic_data(topic) for topic in topics),
            rules=self._prompts.get(PromptKey.PREP_TOPIC_RULES),
            cv_lines=()
            if cv is None
            else tuple(
                CvLineData(
                    text=claim.text,
                    facts=tuple(
                        fact_data(facts[number])
                        for number in claim.fact_ids
                        if number in facts
                    ),
                )
                for claim in cv.claims()
            ),
        )

    async def save_prep_topics(
        self, actor: Actor, job_number: int, items: Sequence[TopicInput]
    ) -> list[TopicData]:
        """Створює нові теми або замінює поля наявних (той самий slug) і прив'язує їх до вакансії
        з прогалиною. Повертає збережені теми в порядку запиту. `InvalidValue` / `NotFound` —
        нічого не збережено."""
        if not items:
            raise InvalidValue("topics", "Список тем порожній.")
        if len(items) > MAX_TOPICS_PER_SAVE:
            raise InvalidValue("topics", f"За раз — до {MAX_TOPICS_PER_SAVE} тем.")
        parsed = [_parse(item) for item in items]
        check_unique_slugs(topic.slug for topic, _ in parsed)
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            job, _ = await _analysed_job(uow, actor.user_id, job_number)
            numbers = [
                await uow.prep_topics.save(
                    actor.user_id, TopicId(self._ids.new()), job.id, topic, gap, now
                )
                for topic, gap in parsed
            ]
            saved = {
                topic.number: topic
                for topic in await uow.prep_topics.all(actor.user_id)
            }
            await uow.commit()
        return [topic_data(saved[number]) for number in numbers]

    async def list_prep_topics(self, actor: Actor) -> list[TopicData]:
        """Усі теми користувача за пріоритетом."""
        async with self._unit_of_work() as uow:
            topics = by_priority(await uow.prep_topics.all(actor.user_id))
        return [topic_data(topic) for topic in topics]

    async def prepare_topic_plan(
        self, actor: Actor, topic_number: int
    ) -> PlanBriefData:
        """Тема з вакансіями, прогалинами й поточним планом + правила плану. `NotFound` — теми
        нема чи вона чужа."""
        async with self._unit_of_work() as uow:
            topic = await _topic(uow, actor.user_id, topic_number)
        return PlanBriefData(
            detail=detail_data(topic),
            rules=self._prompts.get(PromptKey.PREP_PLAN_RULES),
        )

    async def save_topic_plan(
        self, actor: Actor, topic_number: int, items: Sequence[StepInput]
    ) -> TopicDetailData:
        """Замінює невиконані кроки теми новими, виконані лишаються попереду й рахуються в межі
        плану. `InvalidValue` («Крок N: …» або межі плану) / `NotFound` — нічого не змінено."""
        steps = [_parse_step(position, item) for position, item in enumerate(items, 1)]
        async with self._unit_of_work() as uow:
            topic = await _topic(uow, actor.user_id, topic_number)
            check_plan(topic.done, steps)
            await uow.prep_topics.replace_pending_steps(
                actor.user_id,
                topic_number,
                [(StepId(self._ids.new()), step) for step in steps],
            )
            saved = await _topic(uow, actor.user_id, topic_number)
            await uow.commit()
        return detail_data(saved)

    async def get_topic(self, actor: Actor, topic_number: int) -> TopicDetailData:
        async with self._unit_of_work() as uow:
            topic = await _topic(uow, actor.user_id, topic_number)
        return detail_data(topic)

    async def complete_step(
        self, actor: Actor, step_number: int, note: str = ""
    ) -> TopicDetailData:
        """Позначає крок виконаним. Повтор лишає першу дату й замінює нотатку, якщо вона є.
        Повертає тему кроку. Чужий і неіснуючий крок — `NotFound`."""
        note = parse_note(note)
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            topic_number = await uow.prep_topics.complete_step(
                actor.user_id, step_number, note, now
            )
            if topic_number is None:
                raise NotFound(f"Крок {step_number} не знайдено.")
            topic = await _topic(uow, actor.user_id, topic_number)
            await uow.commit()
        return detail_data(topic)

    async def set_topic_ready(
        self, actor: Actor, topic_number: int, *, ready: bool = True
    ) -> TopicDetailData:
        """Тему готовою позначає лише користувач; `ready=False` повертає статус із кроків."""
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            await _topic(uow, actor.user_id, topic_number)
            await uow.prep_topics.set_ready(
                actor.user_id, topic_number, ready=ready, now=now
            )
            topic = await _topic(uow, actor.user_id, topic_number)
            await uow.commit()
        return detail_data(topic)


async def _topic(uow: PrepUnitOfWork, user: UserId, topic_number: int) -> PrepTopic:
    topic = await uow.prep_topics.get(user, topic_number)
    if topic is None:
        raise NotFound(f"Тему {topic_number} не знайдено.")
    return topic


def _parse_step(position: int, item: StepInput) -> NewStep:
    try:
        return NewStep.parse(
            kind=item.kind,
            title=item.title,
            minutes=item.minutes,
            details=item.details,
            resources=[(resource.title, resource.url) for resource in item.resources],
        )
    except InvalidValue as error:
        raise InvalidValue(error.field, f"Крок {position}: {error.message}") from error


async def _analysed_job(
    uow: PrepUnitOfWork, user: UserId, job_number: int
) -> tuple[Job, Analysis]:
    job = await uow.jobs.get(user, job_number)
    if job is None:
        raise NotFound(f"Вакансію {job_number} не знайдено.")
    analysis = await uow.analyses.get(user, job.id)
    if analysis is None:
        raise InvalidValue(
            "job_id",
            f"Вакансію {job_number} ще не проаналізовано: "
            "спершу prepare_analysis → save_analysis.",
        )
    return job, analysis


def _parse(item: TopicInput) -> tuple[NewTopic, str]:
    topic = NewTopic.parse(
        slug=item.slug,
        title=item.title,
        kind=item.kind,
        summary=item.summary,
        deadline=item.deadline,
    )
    return topic, parse_gap(topic.slug, item.gap)


def topic_data(topic: PrepTopic) -> TopicData:
    return TopicData(
        topic_number=topic.number,
        slug=topic.slug,
        title=topic.title,
        kind=topic.kind,
        summary=topic.summary,
        deadline=topic.deadline,
        priority=topic.priority,
        status=topic.status,
        steps_done=len(topic.done),
        steps_total=len(topic.steps),
        minutes_left=topic.minutes_left,
        jobs=tuple(
            TopicJobData(
                job_number=job.job_number,
                title=job.title,
                company=job.company,
                score=job.score,
                gap=job.gap,
            )
            for job in topic.jobs
        ),
    )


def detail_data(topic: PrepTopic) -> TopicDetailData:
    pending = topic.pending
    return TopicDetailData(
        topic=topic_data(topic),
        next_step_number=pending[0].number if pending else None,
        steps=tuple(step_data(step) for step in topic.steps),
    )


def step_data(step: PrepStep) -> StepData:
    return StepData(
        step_number=step.number,
        position=step.position,
        kind=step.kind,
        title=step.title,
        minutes=step.minutes,
        details=step.details,
        resources=tuple(
            ResourceData(title=resource.title, url=resource.url)
            for resource in step.resources
        ),
        done_at=step.done_at,
        note=step.note,
    )
