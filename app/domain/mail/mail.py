"""Пошта: листи, які користувачі пересилають у скриньку застосунку (Gmail), щоб joboffer
бачив відповіді компаній. Скринька лише читається; текст і заголовки листа — недовірені
дані третіх сторін."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from domain.mail.sender_auth import AuthHeaders, SenderAuth

# Більше тексту листа не зберігаємо: відповіді рекрутерів короткі, решта — цитати й підписи.
MAX_TEXT_BYTES = 64 * 1024
# Тема відкинутого листа: від нього зберігаємо адресу відправника й тему, не довшу за це.
MAX_DROPPED_SUBJECT = 200
# Особиста адреса користувача — скринька застосунку з tag: local+<tag>@domain.
TAG_LENGTH = 12
TAG_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
TAG_PATTERN = re.compile(f"[{TAG_ALPHABET}]{{{TAG_LENGTH}}}")
# Перший синк і ресинк після протухлого курсора читають листи за цей час.
RESYNC_WINDOW = timedelta(days=90)
GOOGLE_FORWARDING = "forwarding-noreply@google.com"
# Захист від флуду (адреса для пересилання публічна): листів одного користувача за ковзні
# 24 год до надходження листа зберігається не більше стількох; решта лише рахується.
MAIL_DAILY_LIMIT = 100
MAIL_DAILY_WINDOW = timedelta(hours=24)
# Код у листі Gmail про пересилання: у темі «(#123456789) …» будь-якою мовою, у тексті — після
# «code» / «código» / «код».
FORWARDING_CODE_IN_SUBJECT = re.compile(r"\(#(\d{6,12})\)")
FORWARDING_CODE_IN_TEXT = re.compile(
    r"(?:code|código|код)\D{0,30}?(\d{6,12})", re.IGNORECASE
)
EMAIL_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


class MailCategory(StrEnum):
    """Вид листа за відправником."""

    COMPANY = "company"
    LINKEDIN_ALERT = "linkedin_alert"
    LINKEDIN_APPLICATION = "linkedin_application"
    LINKEDIN_MESSAGE = "linkedin_message"
    FORWARDING_CONFIRMATION = "forwarding_confirmation"
    # Підроблений відправник (DMARC fail): не веде подач.
    SUSPICIOUS = "suspicious"
    OTHER = "other"


# Відправники LinkedIn, яких користувач пересилає (фільтри з гайду M0b).
LINKEDIN_SENDERS = {
    "jobalerts-noreply@linkedin.com": MailCategory.LINKEDIN_ALERT,
    "jobs-noreply@linkedin.com": MailCategory.LINKEDIN_APPLICATION,
    "messages-noreply@linkedin.com": MailCategory.LINKEDIN_MESSAGE,
    "inmail-hit-reply@linkedin.com": MailCategory.LINKEDIN_MESSAGE,
}


class DropReason(StrEnum):
    """Чому синк не зберіг лист. Власник відомий для daily_limit і retired_tag (адреса до
    ротації): такі листи записуються без тексту й видні користувачу; решта — лише в аудиті."""

    NO_TAG = "no_tag"
    UNKNOWN_TAG = "unknown_tag"
    DAILY_LIMIT = "daily_limit"
    RETIRED_TAG = "retired_tag"


class MailboxError(Exception):
    """Скринька недоступна (мережа, відмова API, недійсний токен); повідомлення — без секретів."""


class CursorExpired(MailboxError):
    """Курсор змін протух: скринька вже не віддає зміни від нього — потрібен ресинк."""


@dataclass(frozen=True, slots=True)
class MailInbox:
    """Особиста адреса користувача в скриньці застосунку: tag випадковий, ротація — новий."""

    tag: str
    created_at: datetime
    rotated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MailSyncState:
    """Синк скриньки застосунку: курсор змін (None — ще не синкалась успішно) і остання
    помилка (порожня — останній синк пройшов)."""

    history_id: str | None = None
    synced_at: datetime | None = None
    last_error: str = ""
    failed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Attachment:
    """Лише опис вкладення: сам вміст не зберігається."""

    filename: str
    content_type: str
    size: int


@dataclass(frozen=True, slots=True)
class IncomingMail:
    """Лист зі скриньки після розбору MIME. Адреси — нижнім регістром."""

    id: str  # id листа в скриньці (Gmail message id)
    received_at: datetime
    message_id: str = ""
    in_reply_to: str = ""
    references: tuple[str, ...] = ()
    from_address: str = ""
    from_name: str = ""
    to: tuple[str, ...] = ()
    # Усі Delivered-To: за адресою скриньки з tag лист розкладається по користувачах.
    delivered_to: tuple[str, ...] = ()
    subject: str = ""
    sent_at: datetime | None = None
    # Authentication-Results, ARC-Authentication-Results, ARC-Seal зверху вниз, без розбору.
    auth_headers: AuthHeaders = ()
    text: str = ""
    attachments: tuple[Attachment, ...] = ()
    # Що не вдалося розібрати (решта листа — що вдалося); порожньо — без помилок.
    parse_error: str = ""


@dataclass(frozen=True, slots=True)
class MailChanges:
    """Нові листи скриньки після курсора (у порядку надходження) і курсор для наступного разу."""

    message_ids: tuple[str, ...]
    cursor: str


@dataclass(frozen=True, slots=True)
class DroppedRecord:
    """Відкинутий лист з відомим власником: причина, коли надійшов, відправник і тема.
    Тексту листа тут нема. Відправник і тема — недовірені дані."""

    gmail_id: str
    reason: DropReason
    received_at: datetime
    from_address: str
    subject: str

    @classmethod
    def of(cls, mail: IncomingMail, reason: DropReason) -> DroppedRecord:
        """Запис про відкинутий лист; тема обрізається до MAX_DROPPED_SUBJECT символів."""
        return cls(
            gmail_id=mail.id,
            reason=reason,
            received_at=mail.received_at,
            from_address=mail.from_address,
            subject=mail.subject[:MAX_DROPPED_SUBJECT],
        )


@dataclass(frozen=True, slots=True)
class ForwardingRequest:
    """Лист Gmail про пересилання на особисту адресу: код і адреса-ініціатор. Порожній код —
    коду в листі нема (так Gmail надсилає з 2026-10: лише посилання). Посилання з листа не
    показуємо: лист міг підробити будь-хто, хто знає адресу, а код Gmail перевіряє сам."""

    code: str
    # Адреса, з якої просять пересилати; порожньо — не знайшлась.
    requested_by: str
    received_at: datetime


def clip_text(text: str) -> str:
    """Текст не довший за MAX_TEXT_BYTES у UTF-8; обрізка не рве символ."""
    data = text.encode()
    if len(data) <= MAX_TEXT_BYTES:
        return text
    return data[:MAX_TEXT_BYTES].decode(errors="ignore")


def personal_address(mailbox: str, tag: str) -> str:
    """Адреса, на яку користувач пересилає листи: local+tag@domain скриньки застосунку."""
    local, _, domain = mailbox.lower().partition("@")
    return f"{local}+{tag}@{domain}"


def mail_tag(delivered_to: Sequence[str], mailbox: str) -> str | None:
    """Tag з першого Delivered-To на особисту адресу скриньки застосунку (верхній — останнє
    доставлення); None — лист прийшов не на особисту адресу."""
    local, _, domain = mailbox.lower().partition("@")
    for address in delivered_to:
        name, _, address_domain = address.partition("@")
        base, plus, tag = name.partition("+")
        if (
            plus
            and base == local
            and address_domain == domain
            and TAG_PATTERN.fullmatch(tag)
        ):
            return tag
    return None


def mail_category(from_address: str, sender_auth: SenderAuth) -> MailCategory:
    """Вид листа за відправником і його автентичністю: підроблений (failed) — suspicious;
    підтвердження пересилання — лише від Google з verified, інакше other."""
    if sender_auth is SenderAuth.FAILED:
        return MailCategory.SUSPICIOUS
    if from_address == GOOGLE_FORWARDING:
        if sender_auth is SenderAuth.VERIFIED:
            return MailCategory.FORWARDING_CONFIRMATION
        return MailCategory.OTHER
    if from_address in LINKEDIN_SENDERS:
        return LINKEDIN_SENDERS[from_address]
    domain = from_address.rpartition("@")[2]
    if not domain or domain == "linkedin.com" or domain.endswith(".linkedin.com"):
        return MailCategory.OTHER
    return MailCategory.COMPANY


def forwarding_request(
    subject: str, text: str, received_at: datetime, own_address: str
) -> ForwardingRequest:
    """Код і адреса-ініціатор з листа Gmail про пересилання; коду в листі нема — порожній."""
    found = FORWARDING_CODE_IN_SUBJECT.search(
        subject
    ) or FORWARDING_CODE_IN_TEXT.search(text)
    addresses = (
        address.lower()
        for address in EMAIL_ADDRESS.findall(f"{subject}\n{text}")
        if address.lower() != own_address
    )
    code = "" if found is None else found.group(1)
    return ForwardingRequest(code, next(addresses, ""), received_at)
