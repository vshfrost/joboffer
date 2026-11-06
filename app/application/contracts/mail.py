"""Результати контексту mail: примітиви й незмінні значення домену (значення будує use case)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from domain.mail.forwarded import ForwardedMail
from domain.mail.inbox import (
    DroppedSummary,
    MailList,
    MailSummary,
    ManualSync,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ForwardingData:
    """Лист Gmail про пересилання: код (порожній — Gmail надіслав лише посилання), адреса,
    що просить пересилати, і чи лист стосується чинної адреси (не до ротації)."""

    code: str
    requested_by: str
    received_at: datetime
    current: bool

    @property
    def link_only(self) -> bool:
        return not self.code


@dataclass(frozen=True, slots=True, kw_only=True)
class MailSettingsData:
    """Адреса для пересилання, стан синку скриньки і скільки синків вручну лишилось."""

    address: str
    rotated_at: datetime | None
    synced_at: datetime | None
    sync_failed: bool
    sync_error: str
    manual: ManualSync


@dataclass(frozen=True, slots=True, kw_only=True)
class MailDetailData:
    """Лист для читалки: `text` — недовірений, уже підготовлений для людини."""

    mail: MailSummary
    text: str
    # Є лише в листа-підтвердження пересилання Gmail.
    forwarding: ForwardingData | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MailInboxData:
    """Огляд для get_mail_inbox: адреса, останній код пересилання, останні листи, стан синку
    і лічильники за вікно відкинутих листів."""

    address: str
    forwarding: ForwardingData | None
    recent: tuple[MailSummary, ...]
    synced_at: datetime | None
    sync_failed: bool
    limit_drops: DroppedSummary
    old_address_drops: DroppedSummary
    suspicious: DroppedSummary
    # Листи з `recent`, які власник переслав вручну, за id листа: відправник і тема з блоку.
    forwarded: Mapping[int, ForwardedMail] = field(default_factory=dict)


__all__ = [
    "ForwardingData",
    "MailDetailData",
    "MailInboxData",
    "MailList",
    "MailSettingsData",
]
