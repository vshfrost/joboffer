"""Тул сценаріїв вакансії: `get_scenario`.

Ланцюжок кроків і пропуски — у домені; тут лише схема тулу й мапінг помилок. `job_id` — номер
вакансії в межах користувача.
"""

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.ports.prompts import PromptKey, Prompts
from application.scenarios.use_cases import ScenarioUseCases
from domain.shared.errors import DomainError
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import READ


class ScenarioView(BaseModel):
    name: str
    prompt: str = Field(
        description="What to do in this step; ends with the next-step offer"
    )
    next: str | None = Field(
        description="The following step that applies to this job; null: the chain is finished"
    )
    skip_reason: str | None = Field(
        description="Set: this step does not apply to the job, skip it; null: do it"
    )


def register_scenario_tools(
    agent: MCPServer, use_cases: ScenarioUseCases, prompts: Prompts
) -> None:
    @agent.tool(
        name="get_scenario",
        description=prompts.get(PromptKey.MCP_TOOL_GET_SCENARIO),
        annotations=READ,
    )
    async def get_scenario(name: str, job_id: int | None = None) -> ScenarioView:
        try:
            result = await use_cases.get_scenario(current_actor(), name, job_id)
        except DomainError as error:
            raise ToolError(error.message) from error
        return ScenarioView(
            name=result.name,
            prompt=result.prompt,
            next=result.next,
            skip_reason=result.skip_reason,
        )
