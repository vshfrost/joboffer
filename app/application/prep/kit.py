"""Use cases пакета до інтерв'ю: Claude отримує бриф під вакансію і пише пакет, сервер перевіряє
факти STAR-історій і теми питань та зберігає нову версію.

Вакансія, тема й факт скрізь — за номером у межах користувача; чуже й неіснуюче не відрізняються.
"""

from collections.abc import Callable

from application.analysis.use_cases import analysis_data
from application.contracts.actor import Actor
from application.contracts.kit import (
    KitBriefData,
    KitData,
    KitInput,
    KitQuestionData,
    KitQuestionInput,
    StoryData,
    StoryInput,
)
from application.facts.use_cases import fact_data
from application.jobs.use_cases import job_data
from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.kit import InterviewKitUnitOfWork
from application.ports.prompts import PromptKey, Prompts
from application.prep.use_cases import topic_data
from domain.facts.library import confirmed, require_confirmed
from domain.identity.ids import UserId
from domain.jobs.job import Job
from domain.prep.ids import KitId
from domain.prep.kit import (
    InterviewKit,
    KitQuestion,
    KitVersion,
    StarStory,
    parse_company_question,
)
from domain.prep.topic import by_priority
from domain.shared.errors import InvalidValue, NotFound


class InterviewKitUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], InterviewKitUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        prompts: Prompts,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids
        self._prompts = prompts

    async def prepare_interview_kit(
        self, actor: Actor, job_number: int
    ) -> KitBriefData:
        """Бриф для пакета: вакансія, аналіз (якщо є), її теми за пріоритетом, підтверджені
        факти, правила й попередня версія. `NotFound` — вакансії нема чи вона чужа."""
        user = actor.user_id
        async with self._unit_of_work() as uow:
            job = await _job(uow, user, job_number)
            analysis = await uow.analyses.get(user, job.id)
            topics = by_priority(await uow.prep_topics.all(user))
            facts = confirmed(await uow.facts.all(user))
            previous = await uow.interview_kits.latest(user, job.id)
        return KitBriefData(
            job=job_data(job, None),
            analysis=None if analysis is None else analysis_data(analysis, None),
            topics=tuple(
                topic_data(topic)
                for topic in topics
                if any(linked.job_number == job_number for linked in topic.jobs)
            ),
            confirmed_facts=tuple(fact_data(fact) for fact in facts),
            rules=self._prompts.get(PromptKey.PREP_KIT_RULES),
            previous=None if previous is None else kit_data(previous),
        )

    async def save_interview_kit(
        self, actor: Actor, job_number: int, data: KitInput
    ) -> KitData:
        """Нова версія пакета. `InvalidValue` («Питання N: …», «Історія N: …», «Питання до
        компанії N: …», межі кількості, невідомі чи непідтверджені факти, чужі теми) / `NotFound`
        — нічого не збережено."""
        kit = _parse(data)
        user = actor.user_id
        async with self._unit_of_work() as uow:
            job = await _job(uow, user, job_number)
            require_confirmed(await uow.facts.all(user), kit.fact_ids)
            own = {topic.number for topic in await uow.prep_topics.all(user)}
            unknown = sorted(kit.topic_numbers - own)
            if unknown:
                listed = ", ".join(str(number) for number in unknown)
                raise InvalidValue("topic_id", f"Теми не знайдено: {listed}.")
            saved = await uow.interview_kits.add(
                user, KitId(self._ids.new()), job.id, kit, self._clock.now()
            )
            await uow.commit()
        return kit_data(saved)

    async def latest_interview_kit(
        self, actor: Actor, job_number: int
    ) -> KitData | None:
        """Остання версія пакета вакансії або `None`. `NotFound` — вакансії нема чи вона чужа."""
        async with self._unit_of_work() as uow:
            job = await _job(uow, actor.user_id, job_number)
            latest = await uow.interview_kits.latest(actor.user_id, job.id)
        return None if latest is None else kit_data(latest)


async def _job(uow: InterviewKitUnitOfWork, user: UserId, number: int) -> Job:
    job = await uow.jobs.get(user, number)
    if job is None:
        raise NotFound(f"Вакансію {number} не знайдено.")
    return job


def _parse(data: KitInput) -> InterviewKit:
    """Розбір усього пакета; помилка елемента отримує його позицію (з 1), межі кількості — ні."""
    return InterviewKit(
        questions=tuple(
            _numbered("Питання", position, _question, item)
            for position, item in enumerate(data.questions, 1)
        ),
        stories=tuple(
            _numbered("Історія", position, _story, item)
            for position, item in enumerate(data.stories, 1)
        ),
        company_questions=tuple(
            _numbered("Питання до компанії", position, parse_company_question, item)
            for position, item in enumerate(data.company_questions, 1)
        ),
    )


def _numbered[T, R](label: str, position: int, parse: Callable[[T], R], item: T) -> R:
    try:
        return parse(item)
    except InvalidValue as error:
        raise InvalidValue(
            error.field, f"{label} {position}: {error.message}"
        ) from error


def _question(item: KitQuestionInput) -> KitQuestion:
    return KitQuestion.parse(
        kind=item.kind, question=item.question, topic_number=item.topic_number
    )


def _story(item: StoryInput) -> StarStory:
    return StarStory.parse(
        title=item.title,
        situation=item.situation,
        task=item.task,
        action=item.action,
        result=item.result,
        fact_ids=item.fact_ids,
    )


def kit_data(saved: KitVersion) -> KitData:
    kit = saved.kit
    return KitData(
        kit_number=saved.number,
        job_number=saved.job_number,
        version=saved.version,
        created_at=saved.created_at,
        questions=tuple(
            KitQuestionData(
                kind=question.kind.value,
                question=question.question,
                topic_number=question.topic_number,
            )
            for question in kit.questions
        ),
        stories=tuple(
            StoryData(
                title=story.title,
                situation=story.situation,
                task=story.task,
                action=story.action,
                result=story.result,
                fact_ids=story.fact_ids,
            )
            for story in kit.stories
        ),
        company_questions=kit.company_questions,
    )
