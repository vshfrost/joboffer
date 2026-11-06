"""HTTP промптів для веба: тексти запитів до агента дослівно, ключ — шлях файлу без розширення."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from application.contracts.actor import Actor
from application.ports.prompts import WEB_PROMPT_KEYS, Prompts
from infrastructure.http.auth import HttpAuth


def prompts_router(prompts: Prompts, auth: HttpAuth) -> APIRouter:
    router = APIRouter(prefix="/prompts", tags=["prompts"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    @router.get("")
    async def index(_actor: Caller, response: Response) -> dict[str, str]:
        response.headers["Cache-Control"] = "no-store"
        return {key.value: prompts.get(key) for key in WEB_PROMPT_KEYS}

    return router
