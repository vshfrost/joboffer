"""HTTP онбордингу: кроки з реальних даних, підказки «бачив» і «сховав» (стан — на сервері)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from application.contracts.actor import Actor
from application.onboarding.use_cases import OnboardingUseCases
from infrastructure.http.auth import HttpAuth


class StepModel(BaseModel):
    key: str
    done: bool
    optional: bool


class TipModel(BaseModel):
    key: str
    seen: bool
    dismissed: bool


class OnboardingModel(BaseModel):
    steps: list[StepModel]
    tips: list[TipModel]
    complete: bool


def onboarding_router(onboarding: OnboardingUseCases, auth: HttpAuth) -> APIRouter:
    router = APIRouter(prefix="/onboarding", tags=["onboarding"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    @router.get("")
    async def show(actor: Caller, response: Response) -> OnboardingModel:
        response.headers["Cache-Control"] = "no-store"
        found = await onboarding.get_onboarding(actor)
        return OnboardingModel(
            steps=[
                StepModel(key=s.key, done=s.done, optional=s.optional)
                for s in found.steps
            ],
            tips=[
                TipModel(key=t.key, seen=t.seen, dismissed=t.dismissed)
                for t in found.tips
            ],
            complete=found.complete,
        )

    @router.post("/tips/{key}/seen", status_code=204, deprecated=True)
    async def seen(key: str, actor: Caller) -> Response:
        await onboarding.mark_tip_seen(actor, key)
        return Response(status_code=204)

    @router.post("/tips/{key}/dismiss", status_code=204, deprecated=True)
    async def dismiss(key: str, actor: Caller) -> Response:
        await onboarding.dismiss_tip(actor, key)
        return Response(status_code=204)

    return router
