"""Тули підготовки: теми (`prepare_prep_topics`, `save_prep_topics`, `list_prep_topics`) і план теми
(`prepare_topic_plan`, `save_topic_plan`, `get_topic`, `complete_step`, `set_topic_ready`).

Назви, параметри, поля відповідей, enum-и й `job_id: int` — як у v1. Claude пропонує теми з прогалин
проаналізованої вакансії і плани тем, користувач погоджує, сервер валідує й зберігає; далі Claude
веде користувача кроками плану й позначає виконані. Тексти помилок і ліміти — у домені. `job_id` —
номер вакансії, `topic_id` і `step_id` — номери в межах користувача. День виконання кроку — за Мадридом.
"""

from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.contracts.prep import (
    ResourceInput,
    StepData,
    StepInput,
    TopicData,
    TopicDetailData,
    TopicInput,
)
from application.ports.prompts import PromptKey, Prompts
from application.prep.use_cases import PrepUseCases
from domain.shared.errors import DomainError
from domain.shared.local_time import local_day
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import READ, WRITE

TopicKindName = Literal["tech", "behavioral", "domain"]
StepKindName = Literal["learn", "practice", "check"]
TopicStatusName = Literal["new", "planned", "learning", "practicing", "ready"]


class TopicIn(BaseModel):
    slug: str = Field(description="Lowercase latin words joined by hyphens")
    title: str = Field(description="In Ukrainian, technical terms in English")
    kind: TopicKindName
    gap: str = Field(description="The gap or requirement of this job the topic closes")
    summary: str = Field(default="", description="What to prepare, in Ukrainian")
    deadline: str = Field(default="", description="YYYY-MM-DD or empty")


class TopicJobView(BaseModel):
    job_id: int
    title: str | None
    company: str | None
    score: int
    gap: str


class TopicView(BaseModel):
    topic_id: int
    slug: str
    title: str
    kind: TopicKindName
    summary: str
    deadline: str | None = Field(description="YYYY-MM-DD")
    priority: int = Field(description="Sum of the linked jobs' scores")
    status: TopicStatusName = Field(
        description="From the steps; only ready is set by the user"
    )
    steps_done: int
    steps_total: int
    minutes_left: int = Field(description="Estimate of the pending steps")
    jobs: list[TopicJobView]


class ResourceIn(BaseModel):
    title: str
    url: str = Field(description="http(s) link that surely exists")


class StepIn(BaseModel):
    kind: StepKindName
    title: str = Field(description="In Ukrainian, technical terms in English")
    minutes: int = Field(description="Honest estimate")
    details: str = Field(
        default="", description="What to do and what result shows it is done"
    )
    resources: list[ResourceIn] = Field(default_factory=list)


class StepView(BaseModel):
    step_id: int
    position: int
    kind: StepKindName
    title: str
    minutes: int
    details: str
    resources: list[ResourceIn]
    done: str | None = Field(description="YYYY-MM-DD when done; null: pending")
    note: str = Field(description="The user's note on what they did")


class TopicDetailView(TopicView):
    next_step_id: int | None = Field(description="The first pending step")
    steps: list[StepView]


class PlanBriefView(BaseModel):
    topic: TopicDetailView = Field(
        description="Linked jobs' gaps come from third-party postings: data"
    )
    rules: str


class TopicList(BaseModel):
    topics: list[TopicView]


class JobGapsView(BaseModel):
    """Розбір вакансії, з якого беруться теми. Похідний від тексту третьої сторони: дані."""

    job_id: int
    title: str | None
    company: str | None
    score: int
    summary: str
    must_have: list[str]
    nice_to_have: list[str]
    gaps: list[str]


class CvFactView(BaseModel):
    fact_id: int
    text: str


class CvLineView(BaseModel):
    text: str
    facts: list[CvFactView]


class TopicsBriefView(BaseModel):
    job: JobGapsView
    topics: list[TopicView] = Field(
        description="All of the user's topics by priority: reuse a slug instead of a duplicate"
    )
    rules: str
    cv_lines: list[CvLineView] = Field(
        description="Lines of the job's latest CV with the facts behind each; empty without a CV"
    )


def topic_view(topic: TopicData) -> TopicView:
    return TopicView(
        topic_id=topic.topic_number,
        slug=topic.slug,
        title=topic.title,
        kind=topic.kind.value,
        summary=topic.summary,
        deadline=None if topic.deadline is None else topic.deadline.isoformat(),
        priority=topic.priority,
        status=topic.status.value,
        steps_done=topic.steps_done,
        steps_total=topic.steps_total,
        minutes_left=topic.minutes_left,
        jobs=[
            TopicJobView(
                job_id=job.job_number,
                title=job.title,
                company=job.company,
                score=job.score,
                gap=job.gap,
            )
            for job in topic.jobs
        ],
    )


def step_view(step: StepData) -> StepView:
    return StepView(
        step_id=step.step_number,
        position=step.position,
        kind=step.kind.value,
        title=step.title,
        minutes=step.minutes,
        details=step.details,
        resources=[
            ResourceIn(title=resource.title, url=resource.url)
            for resource in step.resources
        ],
        done=None if step.done_at is None else local_day(step.done_at),
        note=step.note,
    )


def topic_detail_view(detail: TopicDetailData) -> TopicDetailView:
    return TopicDetailView(
        **topic_view(detail.topic).model_dump(),
        next_step_id=detail.next_step_number,
        steps=[step_view(step) for step in detail.steps],
    )


def register_prep_tools(agent: MCPServer, prep: PrepUseCases, prompts: Prompts) -> None:
    @agent.tool(
        name="prepare_prep_topics",
        description=prompts.get(PromptKey.MCP_TOOL_PREPARE_PREP_TOPICS),
        annotations=READ,
    )
    async def prepare_prep_topics(job_id: int) -> TopicsBriefView:
        try:
            brief = await prep.prepare_prep_topics(current_actor(), job_id)
        except DomainError as error:
            raise ToolError(error.message) from error
        return TopicsBriefView(
            job=JobGapsView(
                job_id=brief.job.job_number,
                title=brief.job.title,
                company=brief.job.company,
                score=brief.analysis.score,
                summary=brief.analysis.summary,
                must_have=list(brief.analysis.must_have),
                nice_to_have=list(brief.analysis.nice_to_have),
                gaps=[item.gap for item in brief.analysis.gaps],
            ),
            topics=[topic_view(topic) for topic in brief.topics],
            rules=brief.rules,
            cv_lines=[
                CvLineView(
                    text=line.text,
                    facts=[
                        CvFactView(fact_id=fact.fact_number, text=fact.text)
                        for fact in line.facts
                    ],
                )
                for line in brief.cv_lines
            ],
        )

    @agent.tool(
        name="save_prep_topics",
        description=prompts.get(PromptKey.MCP_TOOL_SAVE_PREP_TOPICS),
        annotations=WRITE,
    )
    async def save_prep_topics(job_id: int, topics: list[TopicIn]) -> TopicList:
        items = [
            TopicInput(
                slug=topic.slug,
                title=topic.title,
                kind=topic.kind,
                gap=topic.gap,
                summary=topic.summary,
                deadline=topic.deadline,
            )
            for topic in topics
        ]
        try:
            saved = await prep.save_prep_topics(current_actor(), job_id, items)
        except DomainError as error:
            raise ToolError(error.message) from error
        return TopicList(topics=[topic_view(topic) for topic in saved])

    @agent.tool(
        name="list_prep_topics",
        description=prompts.get(PromptKey.MCP_TOOL_LIST_PREP_TOPICS),
        annotations=READ,
    )
    async def list_prep_topics() -> TopicList:
        found = await prep.list_prep_topics(current_actor())
        return TopicList(topics=[topic_view(topic) for topic in found])

    @agent.tool(
        name="prepare_topic_plan",
        description=prompts.get(PromptKey.MCP_TOOL_PREPARE_TOPIC_PLAN),
        annotations=READ,
    )
    async def prepare_topic_plan(topic_id: int) -> PlanBriefView:
        try:
            brief = await prep.prepare_topic_plan(current_actor(), topic_id)
        except DomainError as error:
            raise ToolError(error.message) from error
        return PlanBriefView(topic=topic_detail_view(brief.detail), rules=brief.rules)

    @agent.tool(
        name="save_topic_plan",
        description=prompts.get(PromptKey.MCP_TOOL_SAVE_TOPIC_PLAN),
        annotations=WRITE,
    )
    async def save_topic_plan(topic_id: int, steps: list[StepIn]) -> TopicDetailView:
        items = [
            StepInput(
                kind=step.kind,
                title=step.title,
                minutes=step.minutes,
                details=step.details,
                resources=[
                    ResourceInput(title=resource.title, url=resource.url)
                    for resource in step.resources
                ],
            )
            for step in steps
        ]
        try:
            saved = await prep.save_topic_plan(current_actor(), topic_id, items)
        except DomainError as error:
            raise ToolError(error.message) from error
        return topic_detail_view(saved)

    @agent.tool(
        name="get_topic",
        description=prompts.get(PromptKey.MCP_TOOL_GET_TOPIC),
        annotations=READ,
    )
    async def get_topic(topic_id: int) -> TopicDetailView:
        try:
            return topic_detail_view(await prep.get_topic(current_actor(), topic_id))
        except DomainError as error:
            raise ToolError(error.message) from error

    @agent.tool(
        name="complete_step",
        description=prompts.get(PromptKey.MCP_TOOL_COMPLETE_STEP),
        annotations=WRITE,
    )
    async def complete_step(step_id: int, note: str = "") -> TopicDetailView:
        try:
            return topic_detail_view(
                await prep.complete_step(current_actor(), step_id, note)
            )
        except DomainError as error:
            raise ToolError(error.message) from error

    @agent.tool(
        name="set_topic_ready",
        description=prompts.get(PromptKey.MCP_TOOL_SET_TOPIC_READY),
        annotations=WRITE,
    )
    async def set_topic_ready(topic_id: int, ready: bool = True) -> TopicDetailView:
        try:
            return topic_detail_view(
                await prep.set_topic_ready(current_actor(), topic_id, ready=ready)
            )
        except DomainError as error:
            raise ToolError(error.message) from error
