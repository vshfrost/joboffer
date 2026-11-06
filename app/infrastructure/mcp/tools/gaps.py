"""Тул відповіді на прогалину аналізу: `answer_gap`.

Після `save_analysis` агент питає користувача про кожну прогалину її питанням. «Є досвід» —
факти, схвалені користувачем, зберігаються підтвердженими й закривають прогалину; «немає
досвіду» зберігається, щоб не питати вдруге. Тексти помилок і правила — у домені й use case;
`job_id` — номер вакансії в межах користувача.
"""

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.analysis.use_cases import AnalysisUseCases
from application.contracts.analysis import GapAnswerInput
from application.contracts.facts import FactInput
from application.ports.prompts import PromptKey, Prompts
from domain.shared.errors import DomainError
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import WRITE
from infrastructure.mcp.tools.facts import FactDetail, FactIn, fact_detail


class AnsweredGap(BaseModel):
    job_id: int
    gap_number: int
    gap: str = Field(description="Text of the gap the answer is bound to")
    has_experience: bool
    closed: bool = Field(description="true: the gap is covered by the facts below")
    fact_ids: list[int]
    facts: list[FactDetail]


def register_gap_tools(
    agent: MCPServer, use_cases: AnalysisUseCases, prompts: Prompts
) -> None:
    @agent.tool(
        name="answer_gap",
        description=prompts.get(PromptKey.MCP_TOOL_ANSWER_GAP),
        annotations=WRITE,
    )
    async def answer_gap(
        job_id: int,
        gap_number: int,
        has_experience: bool,
        facts: Annotated[list[FactIn], Field(default_factory=list)],
    ) -> AnsweredGap:
        data = GapAnswerInput(
            has_experience=has_experience,
            facts=[FactInput(kind=fact.kind, text=fact.text) for fact in facts],
        )
        try:
            result = await use_cases.answer_gap(
                current_actor(), job_id, gap_number, data
            )
        except DomainError as error:
            raise ToolError(error.message) from error
        return AnsweredGap(
            job_id=result.job_number,
            gap_number=result.gap_number,
            gap=result.answer.gap,
            has_experience=result.answer.has_experience,
            closed=result.answer.has_experience,
            fact_ids=list(result.answer.fact_numbers),
            facts=[fact_detail(fact) for fact in result.facts],
        )
