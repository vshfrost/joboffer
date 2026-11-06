"""HTTP пошти: адреса для пересилання, «Вхідні» (збережені й відкинуті листи, пошук, вид, сторінки),
читалка з кодом пересилання Gmail, синк вручну, зміна адреси.

Усе, що прийшло в листі (відправник, імʼя, тема, текст), — недовірені дані третіх сторін і названо
`untrusted_*`. Текст листа віддається лише в читалці й уже підготовленим для людини (без невидимих
символів, хости посилань у ASCII); клієнт показує його як текст, не як розмітку.
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict

from application.contracts.actor import Actor
from application.contracts.mail import (
    ForwardingData,
    MailDetailData,
    MailSettingsData,
)
from application.mail.inbox import MailUseCases
from domain.mail.inbox import (
    MANUAL_SYNC_LIMIT,
    MailList,
    MailListItem,
    MailPage,
    MailQuery,
    ManualSync,
)
from infrastructure.http.auth import HttpAuth

CategoryName = Literal[
    "company",
    "linkedin_alert",
    "linkedin_application",
    "linkedin_message",
    "forwarding_confirmation",
    "suspicious",
    "other",
]
SenderAuthName = Literal["verified", "failed", "unknown"]
DropReasonName = Literal["daily_limit", "retired_tag"]


class ListParams(BaseModel):
    """Query списку: правила й тексти помилок — у домені (`MailQuery.parse`), не в pydantic."""

    model_config = ConfigDict(extra="forbid")

    q: str = ""
    kind: str = ""
    page: int = 1
    per_page: int = 20


class MailItemModel(BaseModel):
    id: int
    # True — відкинутий лист: рядок без тексту й вердикту, читалки для нього нема.
    dropped: bool
    untrusted_from_address: str
    untrusted_from_name: str
    untrusted_subject: str
    received_at: datetime
    category: CategoryName | None
    sender_auth: SenderAuthName | None
    reason: DropReasonName | None


class MailPageModel(BaseModel):
    number: int
    size: int
    total: int
    first: int
    last: int
    has_newer: bool
    has_older: bool


class MailListModel(BaseModel):
    items: list[MailItemModel]
    page: MailPageModel


class ForwardingModel(BaseModel):
    # Порожній код — Gmail надіслав лише посилання; його користувач відкриває в листі сам.
    code: str
    link_only: bool
    untrusted_requested_by: str
    received_at: datetime
    # False — лист до ротації адреси: код для старої адреси.
    current: bool


class MailDetailModel(MailItemModel):
    untrusted_text: str
    forwarding: ForwardingModel | None


class ManualSyncModel(BaseModel):
    limit: int
    remaining: int
    next_at: datetime | None


class MailSettingsModel(BaseModel):
    address: str
    rotated_at: datetime | None
    synced_at: datetime | None
    sync_failed: bool
    sync_error: str
    manual: ManualSyncModel


def item_model(item: MailListItem) -> MailItemModel:
    return MailItemModel(
        id=item.id,
        dropped=item.dropped,
        untrusted_from_address=item.from_address,
        untrusted_from_name=item.from_name,
        untrusted_subject=item.subject,
        received_at=item.received_at,
        category=None if item.category is None else item.category.value,
        sender_auth=None if item.sender_auth is None else item.sender_auth.value,
        reason=None if item.reason is None else item.reason.value,
    )


def page_model(page: MailPage) -> MailPageModel:
    return MailPageModel(
        number=page.number,
        size=page.size,
        total=page.total,
        first=page.first,
        last=page.last,
        has_newer=page.has_newer,
        has_older=page.has_older,
    )


def list_model(found: MailList) -> MailListModel:
    return MailListModel(
        items=[item_model(item) for item in found.items], page=page_model(found.page)
    )


def forwarding_model(data: ForwardingData) -> ForwardingModel:
    return ForwardingModel(
        code=data.code,
        link_only=data.link_only,
        untrusted_requested_by=data.requested_by,
        received_at=data.received_at,
        current=data.current,
    )


def detail_model(data: MailDetailData) -> MailDetailModel:
    mail = data.mail
    base = item_model(
        MailListItem(
            id=mail.id,
            dropped=False,
            from_address=mail.from_address,
            from_name=mail.from_name,
            subject=mail.subject,
            received_at=mail.received_at,
            category=mail.category,
            sender_auth=mail.sender_auth,
        )
    )
    return MailDetailModel(
        **base.model_dump(),
        untrusted_text=data.text,
        forwarding=None
        if data.forwarding is None
        else forwarding_model(data.forwarding),
    )


def manual_model(manual: ManualSync) -> ManualSyncModel:
    return ManualSyncModel(
        limit=MANUAL_SYNC_LIMIT, remaining=manual.remaining, next_at=manual.next_at
    )


def settings_model(data: MailSettingsData) -> MailSettingsModel:
    return MailSettingsModel(
        address=data.address,
        rotated_at=data.rotated_at,
        synced_at=data.synced_at,
        sync_failed=data.sync_failed,
        sync_error=data.sync_error,
        manual=manual_model(data.manual),
    )


def mail_router(mail: MailUseCases, auth: HttpAuth) -> APIRouter:
    router = APIRouter(prefix="/mail", tags=["mail"])
    Caller = Annotated[Actor, Depends(auth.actor)]

    def private(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    @router.get("")
    async def listing(
        params: Annotated[ListParams, Query()], actor: Caller, response: Response
    ) -> MailListModel:
        private(response)
        query = MailQuery.parse(
            text=params.q, kind=params.kind, page=params.page, per_page=params.per_page
        )
        return list_model(await mail.list_mail(actor, query))

    @router.get("/settings")
    async def settings(actor: Caller, response: Response) -> MailSettingsModel:
        private(response)
        return settings_model(await mail.settings(actor))

    @router.post("/sync")
    async def request_sync(actor: Caller, response: Response) -> ManualSyncModel:
        private(response)
        return manual_model(await mail.request_sync(actor))

    @router.post("/address/rotate")
    async def rotate(actor: Caller, response: Response) -> MailSettingsModel:
        private(response)
        await mail.rotate_address(actor)
        return settings_model(await mail.settings(actor))

    @router.get("/{mail_id}")
    async def details(
        mail_id: int, actor: Caller, response: Response
    ) -> MailDetailModel:
        private(response)
        return detail_model(await mail.get_mail(actor, mail_id))

    return router
