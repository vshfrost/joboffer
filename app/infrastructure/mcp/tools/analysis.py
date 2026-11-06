"""Тули аналізу вакансії: `prepare_analysis` і `save_analysis`.

Назви, параметри, поля відповідей, enum-и, ліміти й `job_id: int` — як у v1. Claude отримує бриф і
пише аналіз за рубрикою, сервер валідує, застосовує жорсткі фільтри профілю й повертає `flags`.
Тексти помилок і ліміти довжин — у домені. `job_id` — номер вакансії в межах користувача.
"""

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.analysis.use_cases import AnalysisUseCases
from application.contracts.analysis import AnalysisData, AnalysisInput, GapInput
from application.ports.prompts import PromptKey, Prompts
from domain.analysis.analysis import MAX_SCORE
from domain.shared.errors import DomainError
from domain.shared.local_time import local_day
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import READ, WRITE
from infrastructure.mcp.tools.facts import FactView, fact_view
from infrastructure.mcp.tools.jobs import JobView, job_view
from infrastructure.mcp.tools.profile import (
    Profile,
    SeniorityName,
    WorkModeName,
    profile_view,
)


class GapIn(BaseModel):
    gap: str
    question: str | None = None


class GapView(BaseModel):
    number: int
    gap: str
    question: str | None


class AnalysisFields(BaseModel):
    """Спільні поля розбору вакансії (без прогалин: на вході й на виході вони різні)."""

    score: int = Field(ge=0, le=MAX_SCORE)
    summary: str
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    seniority: SeniorityName | None = None
    work_mode: WorkModeName | None = None
    location: str | None = None
    languages: list[str] = Field(default_factory=list)
    salary_min_eur: int | None = Field(default=None, description="Gross per year, EUR")
    salary_max_eur: int | None = Field(default=None, description="Gross per year, EUR")
    relocation: bool | None = Field(
        default=None, description="Company offers relocation support"
    )
    reasons: list[str] = Field(default_factory=list)


class AnalysisIn(AnalysisFields):
    """Розбір вакансії за рубрикою з prepare_analysis. null / [] = у вакансії не сказано."""

    gaps: list[GapIn | str] = Field(default_factory=list)
    keyword_facts: dict[str, list[int]] | None = Field(
        default=None,
        description="Keyword (exactly as in keywords) -> fact_ids of the confirmed "
        "facts that back it; leave out keywords no fact backs. null: no map",
    )


class AnalysisView(AnalysisFields):
    gaps: list[GapView] = Field(default_factory=list)
    job_id: int
    filters_passed: bool = Field(description="false: fails the user's hard filters")
    flags: list[str] = Field(description="Which hard filters failed, in Ukrainian")
    updated: str = Field(description="YYYY-MM-DD")


class GapAnswerView(BaseModel):
    gap: str = Field(description="Text of the gap the answer belongs to")
    has_experience: bool
    fact_ids: list[int] = Field(description="Facts that cover the gap; empty for no")
    answered: str = Field(description="YYYY-MM-DD")


class AnalysisBriefView(BaseModel):
    job: JobView
    profile: Profile
    confirmed_facts: list[FactView] = Field(
        description="The only evidence of the user's experience"
    )
    rubric: str
    previous: AnalysisView | None = Field(description="The last saved analysis, if any")
    gap_answers: list[GapAnswerView] = Field(
        description="The user's earlier answers to this job's gap questions: never ask again"
    )


def analysis_view(saved: AnalysisData) -> AnalysisView:
    return AnalysisView(
        job_id=saved.job_number,
        filters_passed=saved.filters_passed,
        flags=list(saved.flags),
        updated=local_day(saved.updated_at),
        score=saved.score,
        summary=saved.summary,
        must_have=list(saved.must_have),
        nice_to_have=list(saved.nice_to_have),
        keywords=list(saved.keywords),
        seniority=None if saved.seniority is None else saved.seniority.value,
        work_mode=None if saved.work_mode is None else saved.work_mode.value,
        location=saved.location,
        languages=list(saved.languages),
        salary_min_eur=saved.salary_min_eur,
        salary_max_eur=saved.salary_max_eur,
        relocation=saved.relocation,
        reasons=list(saved.reasons),
        gaps=[
            GapView(number=g.number, gap=g.gap, question=g.question) for g in saved.gaps
        ],
    )


def register_analysis_tools(
    agent: MCPServer, use_cases: AnalysisUseCases, prompts: Prompts
) -> None:
    @agent.tool(
        name="prepare_analysis",
        description=prompts.get(PromptKey.MCP_TOOL_PREPARE_ANALYSIS),
        annotations=READ,
    )
    async def prepare_analysis(job_id: int) -> AnalysisBriefView:
        try:
            brief = await use_cases.prepare_analysis(current_actor(), job_id)
        except DomainError as error:
            raise ToolError(error.message) from error
        return AnalysisBriefView(
            job=job_view(brief.job),
            profile=profile_view(brief.profile),
            confirmed_facts=[fact_view(fact) for fact in brief.confirmed_facts],
            rubric=brief.rubric,
            previous=None if brief.previous is None else analysis_view(brief.previous),
            gap_answers=[
                GapAnswerView(
                    gap=answer.gap,
                    has_experience=answer.has_experience,
                    fact_ids=list(answer.fact_numbers),
                    answered=local_day(answer.answered_at),
                )
                for answer in brief.gap_answers
            ],
        )

    @agent.tool(
        name="save_analysis",
        description=prompts.get(PromptKey.MCP_TOOL_SAVE_ANALYSIS),
        annotations=WRITE,
    )
    async def save_analysis(job_id: int, analysis: AnalysisIn) -> AnalysisView:
        data = AnalysisInput(
            score=analysis.score,
            summary=analysis.summary,
            must_have=analysis.must_have,
            nice_to_have=analysis.nice_to_have,
            keywords=analysis.keywords,
            seniority=analysis.seniority or "",
            work_mode=analysis.work_mode or "",
            location=analysis.location or "",
            languages=analysis.languages,
            salary_min_eur=analysis.salary_min_eur,
            salary_max_eur=analysis.salary_max_eur,
            relocation=analysis.relocation,
            reasons=analysis.reasons,
            gaps=[
                GapInput(gap=item.gap, question=item.question)
                if isinstance(item, GapIn)
                else item
                for item in analysis.gaps
            ],
            keyword_facts=analysis.keyword_facts,
        )
        try:
            saved = await use_cases.save_analysis(current_actor(), job_id, data)
        except DomainError as error:
            raise ToolError(error.message) from error
        return analysis_view(saved)
