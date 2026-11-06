"""HTTP фактів: бібліотека з лічильниками, оригінал CV, ручне додавання, підтвердження, зміна
й видалення.

`fact_id` у URL і відповідях — номер факту в межах користувача (ціле, з 1); внутрішній UUID
назовні не виходить, `job_id` — номер вакансії користувача. Факти з CV додає лише MCP;
тут користувач додає свій факт вручну (джерело manual, одразу підтверджений).
Поля тіл — рядки: правила й тексти помилок (v1) у домені, не в pydantic.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict

from application.contracts.actor import Actor
from application.contracts.facts import FactData, FactInput
from application.facts.use_cases import FactUseCases
from domain.facts.fact import FactKind, FactSource
from infrastructure.http.auth import HttpAuth


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FactBody(_Body):
    kind: str = ""
    text: str = ""


class ConfirmBody(_Body):
    fact_ids: list[int] = []


class FactModel(BaseModel):
    fact_id: int
    kind: FactKind
    text: str
    confirmed: bool
    source: FactSource
    job_id: int | None
    created_at: datetime
    updated_at: datetime


class KindCountModel(BaseModel):
    kind: FactKind
    total: int
    confirmed: int
    unconfirmed: int


class CountsModel(BaseModel):
    total: int
    confirmed: int
    unconfirmed: int
    kinds: list[KindCountModel]


class FactLibraryModel(BaseModel):
    facts: list[FactModel]
    counts: CountsModel


class ConfirmedModel(BaseModel):
    facts: list[FactModel]


class OriginalCvModel(BaseModel):
    file_name: str | None
    text: str
    saved_at: datetime


def _fact(fact: FactData) -> FactModel:
    return FactModel(
        fact_id=fact.fact_number,
        kind=fact.kind,
        text=fact.text,
        confirmed=fact.confirmed,
        source=fact.source,
        job_id=fact.job_id,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
    )


def facts_router(facts: FactUseCases, auth: HttpAuth) -> APIRouter:
    router = APIRouter(prefix="/facts", tags=["facts"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    def private(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    @router.get("")
    async def library(actor: Caller, response: Response) -> FactLibraryModel:
        private(response)
        found = await facts.list_facts(actor)
        counts = found.counts
        return FactLibraryModel(
            facts=[_fact(fact) for fact in found.facts],
            counts=CountsModel(
                total=counts.total,
                confirmed=counts.confirmed,
                unconfirmed=counts.unconfirmed,
                kinds=[
                    KindCountModel(
                        kind=item.kind,
                        total=item.total,
                        confirmed=item.confirmed,
                        unconfirmed=item.unconfirmed,
                    )
                    for item in counts.kinds
                ],
            ),
        )

    @router.post("", status_code=201)
    async def create(body: FactBody, actor: Caller, response: Response) -> FactModel:
        private(response)
        created = await facts.create_fact(
            actor, FactInput(kind=body.kind, text=body.text)
        )
        return _fact(created)

    @router.get("/original-cv")
    async def original_cv(actor: Caller, response: Response) -> OriginalCvModel:
        private(response)
        cv = await facts.get_original_cv(actor)
        return OriginalCvModel(
            file_name=cv.file_name, text=cv.text, saved_at=cv.saved_at
        )

    @router.post("/confirm")
    async def confirm(
        body: ConfirmBody, actor: Caller, response: Response
    ) -> ConfirmedModel:
        private(response)
        confirmed = await facts.confirm_facts(actor, body.fact_ids)
        return ConfirmedModel(facts=[_fact(fact) for fact in confirmed])

    @router.put("/{fact_id}")
    async def update(
        fact_id: int, body: FactBody, actor: Caller, response: Response
    ) -> FactModel:
        private(response)
        changed = await facts.update_fact(
            actor, fact_id, FactInput(kind=body.kind, text=body.text)
        )
        return _fact(changed)

    @router.delete("/{fact_id}", status_code=204)
    async def delete(fact_id: int, actor: Caller) -> Response:
        await facts.delete_fact(actor, fact_id)
        return Response(status_code=204)

    return router
