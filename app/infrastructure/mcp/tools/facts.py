"""Тули оригіналу CV і фактів: `save_original_cv`, `get_original_cv`, `save_facts`, `list_facts`,
`update_fact`, `confirm_facts`, `delete_fact`.

Назви, параметри, поля відповідей, enum-и й `fact_id: int` — як у v1. Claude розбирає CV, користувач
підтверджує факти. Опис — у каталозі промптів, тексти помилок і дублі — у домені. `fact_id` —
номер факту в межах користувача.
"""

from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.contracts.facts import FactData, FactInput
from application.facts.use_cases import FactUseCases
from application.ports.prompts import PromptKey, Prompts
from domain.shared.errors import DomainError
from domain.shared.local_time import local_day
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import DELETE, READ, WRITE

FactKindName = Literal[
    "experience", "achievement", "project", "skill", "education", "language"
]
FactSourceName = Literal["cv", "chat", "manual"]


class OriginalCvView(BaseModel):
    file_name: str | None
    saved: str = Field(description="YYYY-MM-DD")
    text: str


class SavedCv(BaseModel):
    saved: bool = True


class FactIn(BaseModel):
    kind: FactKindName
    text: str = Field(
        description="One atomic claim, max 500 chars; numbers and names exactly as in the CV"
    )


class FactView(BaseModel):
    fact_id: int
    kind: FactKindName
    text: str
    confirmed: bool


class FactDetail(FactView):
    """Факт у тулах бібліотеки; брифи (аналіз, документи) лишаються з `FactView`."""

    source: FactSourceName
    job_id: int | None = Field(
        description="Number of the job the fact belongs to; null when it is general"
    )


class SavedFacts(BaseModel):
    added: list[FactDetail]
    skipped_duplicates: list[str] = Field(
        description="Texts that were already saved and were skipped"
    )


class FactList(BaseModel):
    facts: list[FactDetail]


class DeletedFact(BaseModel):
    deleted: int


def fact_view(fact: FactData) -> FactView:
    return FactView(
        fact_id=fact.fact_number,
        kind=fact.kind.value,
        text=fact.text,
        confirmed=fact.confirmed,
    )


def fact_detail(fact: FactData) -> FactDetail:
    return FactDetail(
        fact_id=fact.fact_number,
        kind=fact.kind.value,
        text=fact.text,
        confirmed=fact.confirmed,
        source=fact.source.value,
        job_id=fact.job_id,
    )


def register_fact_tools(
    agent: MCPServer, use_cases: FactUseCases, prompts: Prompts
) -> None:
    @agent.tool(
        name="save_original_cv",
        description=prompts.get(PromptKey.MCP_TOOL_SAVE_ORIGINAL_CV),
        annotations=WRITE,
    )
    async def save_original_cv(text: str, file_name: str = "") -> SavedCv:
        try:
            await use_cases.save_original_cv(current_actor(), text, file_name)
        except DomainError as error:
            raise ToolError(error.message) from error
        return SavedCv()

    @agent.tool(
        name="get_original_cv",
        description=prompts.get(PromptKey.MCP_TOOL_GET_ORIGINAL_CV),
        annotations=READ,
    )
    async def get_original_cv() -> OriginalCvView:
        try:
            cv = await use_cases.get_original_cv(current_actor())
        except DomainError as error:
            raise ToolError(error.message) from error
        return OriginalCvView(
            file_name=cv.file_name, saved=local_day(cv.saved_at), text=cv.text
        )

    @agent.tool(
        name="save_facts",
        description=prompts.get(PromptKey.MCP_TOOL_SAVE_FACTS),
        annotations=WRITE,
    )
    async def save_facts(
        facts: list[FactIn], source: FactSourceName = "cv"
    ) -> SavedFacts:
        items = [FactInput(kind=fact.kind, text=fact.text) for fact in facts]
        try:
            saved = await use_cases.save_facts(current_actor(), items, source)
        except DomainError as error:
            raise ToolError(error.message) from error
        return SavedFacts(
            added=[fact_detail(fact) for fact in saved.added],
            skipped_duplicates=list(saved.skipped),
        )

    @agent.tool(
        name="list_facts",
        description=prompts.get(PromptKey.MCP_TOOL_LIST_FACTS),
        annotations=READ,
    )
    async def list_facts(confirmed: bool | None = None) -> FactList:
        library = await use_cases.list_facts(current_actor())
        return FactList(
            facts=[
                fact_detail(fact)
                for fact in library.facts
                if confirmed is None or fact.confirmed == confirmed
            ]
        )

    @agent.tool(
        name="update_fact",
        description=prompts.get(PromptKey.MCP_TOOL_UPDATE_FACT),
        annotations=WRITE,
    )
    async def update_fact(fact_id: int, fact: FactIn) -> FactDetail:
        data = FactInput(kind=fact.kind, text=fact.text)
        try:
            return fact_detail(
                await use_cases.update_fact(current_actor(), fact_id, data)
            )
        except DomainError as error:
            raise ToolError(error.message) from error

    @agent.tool(
        name="confirm_facts",
        description=prompts.get(PromptKey.MCP_TOOL_CONFIRM_FACTS),
        annotations=WRITE,
    )
    async def confirm_facts(fact_ids: list[int]) -> FactList:
        try:
            confirmed = await use_cases.confirm_facts(current_actor(), fact_ids)
        except DomainError as error:
            raise ToolError(error.message) from error
        return FactList(facts=[fact_detail(fact) for fact in confirmed])

    @agent.tool(
        name="delete_fact",
        description=prompts.get(PromptKey.MCP_TOOL_DELETE_FACT),
        annotations=DELETE,
    )
    async def delete_fact(fact_id: int) -> DeletedFact:
        try:
            await use_cases.delete_fact(current_actor(), fact_id)
        except DomainError as error:
            raise ToolError(error.message) from error
        return DeletedFact(deleted=fact_id)
