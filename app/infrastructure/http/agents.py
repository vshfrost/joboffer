"""HTTP агентів: список підключених агентів поточного користувача."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from application.agents.use_cases import AgentUseCases
from application.contracts.actor import Actor
from infrastructure.http.auth import HttpAuth


class AgentModel(BaseModel):
    id: str
    kind: str
    name: str


def agents_router(agents: AgentUseCases, auth: HttpAuth) -> APIRouter:
    router = APIRouter(prefix="/agents", tags=["agents"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    @router.get("")
    async def index(actor: Caller, response: Response) -> list[AgentModel]:
        response.headers["Cache-Control"] = "no-store"
        return [
            AgentModel(id=a.id, kind=a.kind, name=a.name)
            for a in await agents.list_agents(actor)
        ]

    return router
