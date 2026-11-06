"""HTTP подач: подача вакансії, «Я подався» / зміна даних, перехід статусу.

`job_id` у URL і відповідях — номер вакансії в межах користувача. Поля тіл — рядки: правила й
тексти помилок (v1) у домені, не в pydantic. Відповідь містить `allowed_transitions` з домену,
щоб інтерфейс не дублював матрицю переходів.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict

from application.applications.use_cases import ApplicationUseCases
from application.contracts.actor import Actor
from application.contracts.applications import ApplicationData, ApplicationInput
from domain.shared.errors import NotFound
from infrastructure.http.auth import HttpAuth

ApplicationStatusName = Literal[
    "applied", "replied", "interview", "offer", "rejected", "withdrawn"
]
ChannelName = Literal["email", "ats", "linkedin", "referral"]
AtsName = Literal[
    "greenhouse", "lever", "ashby", "workable", "smartrecruiters", "other"
]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApplicationBody(_Body):
    channel: str
    applied_on: str = ""
    ats: str = ""
    company_domains: list[str] = []
    company_emails: list[str] = []


class StatusBody(_Body):
    status: str


class ApplicationModel(BaseModel):
    job_id: int
    status: ApplicationStatusName
    applied_on: date
    channel: ChannelName
    ats: AtsName | None
    company_domains: list[str]
    company_emails: list[str]
    status_changed_at: datetime
    # Куди подачу можна рухати зараз; бекенд перевіряє перехід повторно.
    allowed_transitions: list[ApplicationStatusName]


def application_model(data: ApplicationData) -> ApplicationModel:
    return ApplicationModel(
        job_id=data.job_number,
        status=data.status.value,
        applied_on=data.applied_on,
        channel=data.channel.value,
        ats=None if data.ats is None else data.ats.value,
        company_domains=list(data.company_domains),
        company_emails=list(data.company_emails),
        status_changed_at=data.status_changed_at,
        allowed_transitions=[s.value for s in data.allowed_transitions],
    )


def applications_router(applications: ApplicationUseCases, auth: HttpAuth) -> APIRouter:
    router = APIRouter(prefix="/jobs", tags=["applications"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    def private(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    @router.get("/{job_id}/application")
    async def details(
        job_id: int, actor: Caller, response: Response
    ) -> ApplicationModel:
        private(response)
        found = await applications.get_application(actor, job_id)
        if found is None:
            raise NotFound(f"Подачі на вакансію {job_id} нема.")
        return application_model(found)

    @router.put("/{job_id}/application")
    async def mark_applied(
        job_id: int, body: ApplicationBody, actor: Caller, response: Response
    ) -> ApplicationModel:
        private(response)
        saved = await applications.mark_applied(
            actor,
            job_id,
            ApplicationInput(
                channel=body.channel,
                applied_on=body.applied_on,
                ats=body.ats,
                company_domains=body.company_domains,
                company_emails=body.company_emails,
            ),
        )
        return application_model(saved)

    @router.post("/{job_id}/application/status")
    async def set_status(
        job_id: int, body: StatusBody, actor: Caller, response: Response
    ) -> ApplicationModel:
        private(response)
        moved = await applications.set_application_status(actor, job_id, body.status)
        return application_model(moved)

    return router
