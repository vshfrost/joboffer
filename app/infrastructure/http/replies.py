"""HTTP відповідей на подачі для вебу: три черги з лічильниками, пошук і сторінки, деталі з подачами
власника, превʼю ефекту розбору й сам розбір.

Розбір іде через ті самі use cases і правила, що MCP `review_reply`; повторне редагування розібраного
інтерфейс не пропонує. Усе, що прийшло в листі (відправник, імʼя, тема, текст), — недовірені дані
третіх сторін і названо `untrusted_*`; текст віддається лише в деталях і вже підготовленим для людини.
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict

from application.contracts.actor import Actor
from application.contracts.replies import ReplyDetailData, ReviewInput
from application.mail.replies import ReplyUseCases
from domain.mail.board import ReplyBoard, ReplyCounts, ReplyQuery, ReviewEffect
from domain.mail.forwarded import ForwardedMail
from domain.mail.replies import AppliedJob, Reply, ReplyJob
from infrastructure.http.applications import (
    ApplicationModel,
    ApplicationStatusName,
    application_model,
)
from infrastructure.http.auth import HttpAuth
from infrastructure.http.mail import MailPageModel, SenderAuthName, page_model

QueueName = Literal["matched", "unmatched", "reviewed"]
ReplyTypeName = Literal[
    "auto_confirmation", "rejection", "invitation", "assignment", "other"
]
ConfidenceName = Literal["high", "medium", "low"]
MatchedByName = Literal["thread", "email", "domain", "ats", "name"]


class ListParams(BaseModel):
    """Query черги: правила й тексти помилок — у домені (`ReplyQuery.parse`), не в pydantic."""

    model_config = ConfigDict(extra="forbid")

    queue: str = "matched"
    q: str = ""
    page: int = 1
    per_page: int = 20


class PreviewParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    job_id: int | None = None


class ReviewBody(BaseModel):
    """`job_id` null — лист не про жодну подачу; тип розбирає домен."""

    model_config = ConfigDict(extra="forbid")

    type: str
    job_id: int | None = None


class JobModel(BaseModel):
    job_id: int
    title: str | None
    company: str | None
    # Статус подачі; null — подачі на цю вакансію нема.
    status: ApplicationStatusName | None


class ApplicationRefModel(BaseModel):
    """Подача власника, з якої обирається вакансія для відповіді."""

    job_id: int
    title: str | None
    company: str | None
    status: ApplicationStatusName


class ForwardedModel(BaseModel):
    """Ручне пересилання: відправник і тема з блоку пересланого листа, не перевірені."""

    untrusted_from_address: str
    untrusted_from_name: str
    untrusted_subject: str


class ReplyItemModel(BaseModel):
    id: int
    untrusted_from_address: str
    untrusted_from_name: str
    untrusted_subject: str
    received_at: datetime
    sender_auth: SenderAuthName
    # Збіг (для розібраної — підтверджена вакансія); null — лист не про подачу.
    job: JobModel | None
    confidence: ConfidenceName | None
    matched_by: MatchedByName | None
    # Підказка типу за ключовими словами; тип підтверджує користувач.
    suggested_type: ReplyTypeName
    type: ReplyTypeName | None
    reviewed_at: datetime | None
    manual_forward: ForwardedModel | None


class ReplyDetailModel(ReplyItemModel):
    untrusted_text: str
    applications: list[ApplicationRefModel]


class CountsModel(BaseModel):
    matched: int
    unmatched: int
    reviewed: int


class BoardModel(BaseModel):
    queue: QueueName
    items: list[ReplyItemModel]
    page: MailPageModel
    counts: CountsModel


class PreviewModel(BaseModel):
    job_id: int | None
    # Статус подачі зараз і після розбору (той самий — без змін); null — розбір без вакансії.
    current_status: ApplicationStatusName | None
    status_after: ApplicationStatusName | None
    changes: bool


class ReviewedModel(BaseModel):
    reply: ReplyItemModel
    application: ApplicationModel | None


def forwarded_model(forwarded: ForwardedMail | None) -> ForwardedModel | None:
    if forwarded is None:
        return None
    return ForwardedModel(
        untrusted_from_address=forwarded.from_address,
        untrusted_from_name=forwarded.from_name,
        untrusted_subject=forwarded.subject,
    )


def job_model(job: ReplyJob | None) -> JobModel | None:
    if job is None:
        return None
    return JobModel(
        job_id=job.job_number,
        title=job.title,
        company=job.company,
        status=None if job.status is None else job.status.value,
    )


def item_model(reply: Reply) -> ReplyItemModel:
    mail = reply.mail
    return ReplyItemModel(
        id=reply.id,
        untrusted_from_address=mail.from_address,
        untrusted_from_name=mail.from_name,
        untrusted_subject=mail.subject,
        received_at=mail.received_at,
        sender_auth=mail.sender_auth.value,
        job=job_model(reply.job),
        confidence=None if reply.confidence is None else reply.confidence.value,
        matched_by=None if reply.matched_by is None else reply.matched_by.value,
        suggested_type=reply.suggested_type.value,
        type=None if reply.type is None else reply.type.value,
        reviewed_at=reply.reviewed_at,
        manual_forward=forwarded_model(reply.forwarded),
    )


def application_ref(job: AppliedJob) -> ApplicationRefModel:
    return ApplicationRefModel(
        job_id=job.job_number,
        title=job.title,
        company=job.company,
        status=job.status.value,
    )


def detail_model(data: ReplyDetailData) -> ReplyDetailModel:
    return ReplyDetailModel(
        **item_model(data.reply).model_dump(),
        untrusted_text=data.reply.text,
        applications=[application_ref(job) for job in data.applications],
    )


def counts_model(counts: ReplyCounts) -> CountsModel:
    return CountsModel(
        matched=counts.matched, unmatched=counts.unmatched, reviewed=counts.reviewed
    )


def board_model(query: ReplyQuery, board: ReplyBoard) -> BoardModel:
    return BoardModel(
        queue=query.queue.value,
        items=[item_model(reply) for reply in board.items],
        page=page_model(board.page),
        counts=counts_model(board.counts),
    )


def preview_model(effect: ReviewEffect) -> PreviewModel:
    return PreviewModel(
        job_id=effect.job_number,
        current_status=None if effect.current is None else effect.current.value,
        status_after=None if effect.after is None else effect.after.value,
        changes=effect.changes,
    )


def replies_router(replies: ReplyUseCases, auth: HttpAuth) -> APIRouter:
    router = APIRouter(prefix="/replies", tags=["replies"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    def private(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    @router.get("")
    async def listing(
        params: Annotated[ListParams, Query()], actor: Caller, response: Response
    ) -> BoardModel:
        private(response)
        query = ReplyQuery.parse(
            queue=params.queue,
            text=params.q,
            page=params.page,
            per_page=params.per_page,
        )
        return board_model(query, await replies.board(actor, query))

    @router.get("/{reply_id}")
    async def details(
        reply_id: int, actor: Caller, response: Response
    ) -> ReplyDetailModel:
        private(response)
        return detail_model(await replies.get_reply(actor, reply_id))

    @router.get("/{reply_id}/preview")
    async def preview(
        reply_id: int,
        params: Annotated[PreviewParams, Query()],
        actor: Caller,
        response: Response,
    ) -> PreviewModel:
        private(response)
        data = ReviewInput(
            reply_id=reply_id, type=params.type, job_number=params.job_id
        )
        return preview_model(await replies.preview_review(actor, data))

    @router.post("/{reply_id}/review")
    async def review(
        reply_id: int, body: ReviewBody, actor: Caller, response: Response
    ) -> ReviewedModel:
        private(response)
        data = ReviewInput(reply_id=reply_id, type=body.type, job_number=body.job_id)
        reviewed = await replies.review_reply(actor, data)
        application = reviewed.application
        return ReviewedModel(
            reply=item_model(reviewed.reply),
            application=None if application is None else application_model(application),
        )

    return router
