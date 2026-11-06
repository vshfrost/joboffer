"""HTTP підготовки для вебу: реєстр тем, сторінка теми, «виконано» з нотаткою, «готово», підготовка
до вакансії і пакет до інтерв'ю.

`topic_id`, `step_id`, `job_id` — номери в межах користувача (цілі, з 1). Теми, плани, питання й
пакети створює лише Claude через MCP; у вебі їх читають і ведуть прогрес. Ключа оцінки питань квізу
тут нема ніде. Чуже й неіснуюче — 404 (однаково).

Час — ISO UTC; поруч `done_on` / `created_on` — той самий момент як день за Мадридом.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict

from application.contracts.actor import Actor
from application.contracts.kit import KitData
from application.contracts.prep import StepData, TopicData, TopicJobData
from application.contracts.prep_web import (
    JobPrepData,
    TopicBoardData,
    TopicPageData,
    TopicRowData,
)
from application.contracts.quiz import QuizCountData
from application.prep.kit import InterviewKitUseCases
from application.prep.web import PrepWebUseCases
from domain.shared.errors import NotFound
from domain.shared.local_time import local_day
from infrastructure.http.auth import HttpAuth

TopicKindName = Literal["tech", "behavioral", "domain"]
TopicStatusName = Literal["new", "planned", "learning", "practicing", "ready"]
StepKindName = Literal["learn", "practice", "check"]
KitQuestionKindName = Literal["technical", "behavioral"]


class DoneBody(BaseModel):
    """`note` обов'язкова; порожня — без нотатки (стара лишається). Межі — у домені."""

    model_config = ConfigDict(extra="forbid")

    note: str


class ReadyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool


class QuizModel(BaseModel):
    """Питань у темі (чи в усіх темах) і скільки з них на повторенні сьогодні за Мадридом."""

    total: int
    due: int


class TopicJobModel(BaseModel):
    job_id: int
    title: str | None
    company: str | None
    score: int
    # Прогалина вакансії, яку закриває тема.
    gap: str


class ResourceModel(BaseModel):
    title: str
    url: str


class StepModel(BaseModel):
    step_id: int
    position: int
    kind: StepKindName
    title: str
    minutes: int
    details: str
    resources: list[ResourceModel]
    # Коли виконано; null — ні. `done_on` — день виконання за Мадридом.
    done_at: datetime | None
    done_on: str | None
    note: str


class TopicRowModel(BaseModel):
    topic_id: int
    slug: str
    title: str
    kind: TopicKindName
    summary: str
    status: TopicStatusName
    # Готова тема — 100, інакше частка виконаних кроків (без плану — 0).
    percent: int
    steps_done: int
    steps_total: int
    # Хвилини невиконаних кроків.
    minutes_left: int
    deadline: date | None
    # Сума скорів вакансій теми; за нею впорядковано реєстр.
    priority: int
    jobs: list[TopicJobModel]
    quiz: QuizModel


class TopicModel(TopicRowModel):
    # Перший невиконаний крок; null — кроків нема чи всі виконано.
    next_step_id: int | None
    steps: list[StepModel]


class BoardModel(BaseModel):
    topics: list[TopicRowModel]
    quiz: QuizModel


class JobPrepModel(BaseModel):
    # Середній % тем вакансії; null — тем нема.
    readiness: int | None
    topics: list[TopicRowModel]


class KitQuestionModel(BaseModel):
    kind: KitQuestionKindName
    question: str
    # Тема з реєстру; null — питання не про тему.
    topic_id: int | None


class StoryModel(BaseModel):
    title: str
    situation: str
    task: str
    action: str
    result: str
    # Номери підтверджених фактів, на яких побудована історія.
    fact_ids: list[int]


class KitModel(BaseModel):
    kit_id: int
    job_id: int
    # Версія пакета вакансії: 1, 2, …
    version: int
    created_at: datetime
    created_on: str
    questions: list[KitQuestionModel]
    stories: list[StoryModel]
    company_questions: list[str]


def quiz_model(quiz: QuizCountData) -> QuizModel:
    return QuizModel(total=quiz.total, due=quiz.due)


def job_model(job: TopicJobData) -> TopicJobModel:
    return TopicJobModel(
        job_id=job.job_number,
        title=job.title,
        company=job.company,
        score=job.score,
        gap=job.gap,
    )


def step_model(step: StepData) -> StepModel:
    return StepModel(
        step_id=step.step_number,
        position=step.position,
        kind=step.kind.value,
        title=step.title,
        minutes=step.minutes,
        details=step.details,
        resources=[
            ResourceModel(title=resource.title, url=resource.url)
            for resource in step.resources
        ],
        done_at=step.done_at,
        done_on=None if step.done_at is None else local_day(step.done_at),
        note=step.note,
    )


def row_model(row: TopicRowData) -> TopicRowModel:
    return _row(row.topic, row.percent, row.quiz)


def _row(topic: TopicData, percent: int, quiz: QuizCountData) -> TopicRowModel:
    return TopicRowModel(
        topic_id=topic.topic_number,
        slug=topic.slug,
        title=topic.title,
        kind=topic.kind.value,
        summary=topic.summary,
        status=topic.status.value,
        percent=percent,
        steps_done=topic.steps_done,
        steps_total=topic.steps_total,
        minutes_left=topic.minutes_left,
        deadline=topic.deadline,
        priority=topic.priority,
        jobs=[job_model(job) for job in topic.jobs],
        quiz=quiz_model(quiz),
    )


def topic_model(page: TopicPageData) -> TopicModel:
    detail = page.detail
    return TopicModel(
        **_row(detail.topic, page.percent, page.quiz).model_dump(),
        next_step_id=detail.next_step_number,
        steps=[step_model(step) for step in detail.steps],
    )


def board_model(board: TopicBoardData) -> BoardModel:
    return BoardModel(
        topics=[row_model(row) for row in board.topics], quiz=quiz_model(board.quiz)
    )


def job_prep_model(prep: JobPrepData) -> JobPrepModel:
    return JobPrepModel(
        readiness=prep.readiness, topics=[row_model(row) for row in prep.topics]
    )


def kit_model(kit: KitData) -> KitModel:
    return KitModel(
        kit_id=kit.kit_number,
        job_id=kit.job_number,
        version=kit.version,
        created_at=kit.created_at,
        created_on=local_day(kit.created_at),
        questions=[
            KitQuestionModel(
                kind=question.kind,
                question=question.question,
                topic_id=question.topic_number,
            )
            for question in kit.questions
        ],
        stories=[
            StoryModel(
                title=story.title,
                situation=story.situation,
                task=story.task,
                action=story.action,
                result=story.result,
                fact_ids=list(story.fact_ids),
            )
            for story in kit.stories
        ],
        company_questions=list(kit.company_questions),
    )


def prep_router(
    web: PrepWebUseCases, kits: InterviewKitUseCases, auth: HttpAuth
) -> APIRouter:
    router = APIRouter(tags=["prep"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    def private(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    @router.get("/prep/topics")
    async def topics(actor: Caller, response: Response) -> BoardModel:
        private(response)
        return board_model(await web.topics(actor))

    @router.get("/prep/topics/{topic_id}")
    async def topic(topic_id: int, actor: Caller, response: Response) -> TopicModel:
        private(response)
        return topic_model(await web.topic(actor, topic_id))

    @router.post("/prep/steps/{step_id}/done")
    async def done(
        step_id: int, body: DoneBody, actor: Caller, response: Response
    ) -> TopicModel:
        private(response)
        return topic_model(await web.complete_step(actor, step_id, body.note))

    @router.put("/prep/topics/{topic_id}/ready")
    async def ready(
        topic_id: int, body: ReadyBody, actor: Caller, response: Response
    ) -> TopicModel:
        private(response)
        return topic_model(await web.set_topic_ready(actor, topic_id, ready=body.ready))

    @router.get("/jobs/{job_id}/prep")
    async def job_prep(job_id: int, actor: Caller, response: Response) -> JobPrepModel:
        private(response)
        return job_prep_model(await web.job_prep(actor, job_id))

    @router.get("/jobs/{job_id}/interview-kit")
    async def interview_kit(job_id: int, actor: Caller, response: Response) -> KitModel:
        private(response)
        kit = await kits.latest_interview_kit(actor, job_id)
        if kit is None:
            raise NotFound(f"Пакет до вакансії {job_id} не знайдено.")
        return kit_model(kit)

    return router
