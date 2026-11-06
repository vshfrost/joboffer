"""Тули пакета до інтерв'ю: `prepare_interview_kit`, `save_interview_kit`.

Назви, параметри й поля відповідей — як у v1. Claude отримує бриф під вакансію (текст, аналіз,
теми підготовки, підтверджені факти, правила, попередня версія), пише питання, STAR-історії й
питання до компанії; сервер перевіряє межі, факти й теми та зберігає нову версію. `job_id`,
`topic_id` і `fact_ids` — номери користувача; `kit_id` — номер версії пакета; `created` — день за
Мадридом.
"""

from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.contracts.kit import (
    KitData,
    KitInput,
    KitQuestionInput,
    StoryInput,
)
from application.ports.prompts import PromptKey, Prompts
from application.prep.kit import InterviewKitUseCases
from domain.shared.errors import DomainError
from domain.shared.local_time import local_day
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import CREATE, READ
from infrastructure.mcp.tools.analysis import AnalysisView, analysis_view
from infrastructure.mcp.tools.facts import FactView, fact_view
from infrastructure.mcp.tools.jobs import JobView, job_view
from infrastructure.mcp.tools.prep import TopicView, topic_view

KitQuestionKindName = Literal["technical", "behavioral"]


class KitQuestionIn(BaseModel):
    kind: KitQuestionKindName
    question: str = Field(description="In English, as the interviewer asks it")
    topic_id: int | None = Field(
        default=None, description="The prep topic that prepares the answer; null: none"
    )


class StarStoryIn(BaseModel):
    title: str = Field(description="Short name of the story")
    situation: str
    task: str
    action: str
    result: str
    fact_ids: list[int] = Field(description="Confirmed facts the story rests on, 1–10")


class KitView(BaseModel):
    kit_id: int
    job_id: int
    version: int
    created: str = Field(description="YYYY-MM-DD")
    questions: list[KitQuestionIn]
    stories: list[StarStoryIn]
    company_questions: list[str]


class KitBriefView(BaseModel):
    job: JobView
    analysis: AnalysisView | None = Field(
        description="Must-haves and gaps; null: not analysed yet"
    )
    topics: list[TopicView] = Field(
        description="The user's prep topics for this job, by priority: use their topic_id"
    )
    confirmed_facts: list[FactView] = Field(
        description="The only evidence of the user's experience; cite their fact_id"
    )
    rules: str
    previous: KitView | None = Field(description="The last saved kit, if any")


def kit_view(kit: KitData) -> KitView:
    return KitView(
        kit_id=kit.kit_number,
        job_id=kit.job_number,
        version=kit.version,
        created=local_day(kit.created_at),
        questions=[
            KitQuestionIn(
                kind=question.kind,
                question=question.question,
                topic_id=question.topic_number,
            )
            for question in kit.questions
        ],
        stories=[
            StarStoryIn(
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


def register_interview_tools(
    agent: MCPServer, kits: InterviewKitUseCases, prompts: Prompts
) -> None:
    @agent.tool(
        name="prepare_interview_kit",
        description=prompts.get(PromptKey.MCP_TOOL_PREPARE_INTERVIEW_KIT),
        annotations=READ,
    )
    async def prepare_interview_kit(job_id: int) -> KitBriefView:
        try:
            brief = await kits.prepare_interview_kit(current_actor(), job_id)
        except DomainError as error:
            raise ToolError(error.message) from error
        return KitBriefView(
            job=job_view(brief.job),
            analysis=None if brief.analysis is None else analysis_view(brief.analysis),
            topics=[topic_view(topic) for topic in brief.topics],
            confirmed_facts=[fact_view(fact) for fact in brief.confirmed_facts],
            rules=brief.rules,
            previous=None if brief.previous is None else kit_view(brief.previous),
        )

    @agent.tool(
        name="save_interview_kit",
        description=prompts.get(PromptKey.MCP_TOOL_SAVE_INTERVIEW_KIT),
        annotations=CREATE,
    )
    async def save_interview_kit(
        job_id: int,
        questions: list[KitQuestionIn],
        stories: list[StarStoryIn],
        company_questions: list[str],
    ) -> KitView:
        data = KitInput(
            questions=[
                KitQuestionInput(
                    kind=question.kind,
                    question=question.question,
                    topic_number=question.topic_id,
                )
                for question in questions
            ],
            stories=[
                StoryInput(
                    title=story.title,
                    situation=story.situation,
                    task=story.task,
                    action=story.action,
                    result=story.result,
                    fact_ids=story.fact_ids,
                )
                for story in stories
            ],
            company_questions=company_questions,
        )
        try:
            return kit_view(
                await kits.save_interview_kit(current_actor(), job_id, data)
            )
        except DomainError as error:
            raise ToolError(error.message) from error
