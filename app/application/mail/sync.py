"""Синк пошти: нові листи скриньки застосунку розкладаються по користувачах за tag
особистої адреси, листи компаній зіставляються з подачами. Одна транзакція: листи, їх
зіставлення й новий курсор зберігаються разом, тож після збою наступний синк повторює те саме
(збережені листи пропускаються). Текст листів — недовірені дані."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from application.mail.alerts import AlertReport, import_alerts
from application.mail.replies import MatchReport, match_replies
from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.mail import Mailbox, MailUnitOfWork
from domain.identity.ids import UserId
from domain.mail.mail import (
    MAIL_DAILY_LIMIT,
    MAIL_DAILY_WINDOW,
    RESYNC_WINDOW,
    CursorExpired,
    DroppedRecord,
    DropReason,
    IncomingMail,
    MailboxError,
    MailSyncState,
    mail_category,
    mail_tag,
)
from domain.mail.sender_auth import sender_auth


@dataclass(frozen=True, slots=True)
class DroppedMail:
    """Лист, який синк не зберіг: без особистої адреси (no_tag), на адресу, якої не було
    (unknown_tag), на адресу до ротації (retired_tag) або понад добовий ліміт власника
    (daily_limit). Для аудиту — без вмісту."""

    gmail_id: str
    reason: DropReason


@dataclass(slots=True)
class SyncReport:
    # Синк уже йде в іншому процесі — цей нічого не робив.
    locked: bool = False
    # Курсора не було або він протух: перечитано листи за RESYNC_WINDOW.
    resynced: bool = False
    stored: int = 0
    # Уже збережені чи відкинуті з відомим власником раніше (повтор після збою, ресинк).
    known: int = 0
    # Зникли зі скриньки між списком змін і читанням.
    gone: int = 0
    dropped: list[DroppedMail] = field(default_factory=list)
    # Зіставлення нових листів компаній з подачами (окрема транзакція після збереження).
    replies: MatchReport = field(default_factory=MatchReport)
    # Листи linkedin_alert → вакансії (у тій самій транзакції).
    alerts: AlertReport = field(default_factory=AlertReport)


class MailSyncUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], MailUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids

    async def sync_mail(self, mailbox: Mailbox, address: str) -> SyncReport:
        """Нові листи скриньки `address` → листи користувачів. Одна транзакція: листи й новий
        курсор зберігаються разом. Збій скриньки (`MailboxError`) записується в стан синку й
        летить далі; синк, що вже йде в іншому процесі, нічого не робить (`locked`)."""
        now = self._clock.now()
        address = address.lower()
        try:
            async with self._unit_of_work() as uow:
                if not await uow.mail_sync.lock():
                    return SyncReport(locked=True)
                report = SyncReport()
                ids, cursor = await _new_mail(
                    mailbox, await uow.mail_sync.get(address), now, report
                )
                known = await uow.mail_messages.known(ids)
                known |= await uow.mail_dropped.known(ids)
                report.known = sum(1 for gmail_id in ids if gmail_id in known)
                for gmail_id in ids:
                    if gmail_id not in known:
                        mail = await mailbox.message(gmail_id)
                        await _store(uow, mail, gmail_id, address, report)
                report.replies = await match_replies(uow, now)
                report.alerts = await import_alerts(uow, self._ids, now)
                await uow.mail_sync.save(address, cursor, now)
                await uow.mail_sync_requests.mark_handled(now)
                await uow.commit()
        except MailboxError as exc:
            async with self._unit_of_work() as uow:
                await uow.mail_sync.fail(address, str(exc), now)
                await uow.commit()
            raise
        return report


async def _new_mail(
    mailbox: Mailbox, state: MailSyncState | None, now: datetime, report: SyncReport
) -> tuple[Sequence[str], str]:
    """Id нових листів і курсор, який стане поточним після їх збереження."""
    if state is None or not state.history_id:
        return await _resync(mailbox, now, report)
    try:
        changes = await mailbox.changes(state.history_id)
    except CursorExpired:
        return await _resync(mailbox, now, report)
    return changes.message_ids, changes.cursor


async def _resync(
    mailbox: Mailbox, now: datetime, report: SyncReport
) -> tuple[Sequence[str], str]:
    report.resynced = True
    # Курсор — до списку: лист, що прийде між ними, віддасть наступний синк.
    cursor = await mailbox.profile_cursor()
    return await mailbox.since(now - RESYNC_WINDOW), cursor


async def _store(
    uow: MailUnitOfWork,
    mail: IncomingMail | None,
    gmail_id: str,
    address: str,
    report: SyncReport,
) -> None:
    if mail is None:
        report.gone += 1
        return
    tag = mail_tag(mail.delivered_to, address)
    owner = await uow.mail_inboxes.owner(tag) if tag else None
    if owner is None:
        retired = await uow.mail_inboxes.retired_owner(tag) if tag else None
        if retired is not None:
            await _drop(uow, retired, mail, DropReason.RETIRED_TAG, report)
            return
        reason = DropReason.UNKNOWN_TAG if tag else DropReason.NO_TAG
        report.dropped.append(DroppedMail(gmail_id, reason))
        return
    received = mail.received_at
    day = await uow.mail_messages.count_received(
        owner, received - MAIL_DAILY_WINDOW, received
    )
    if day >= MAIL_DAILY_LIMIT:
        await _drop(uow, owner, mail, DropReason.DAILY_LIMIT, report)
        return
    auth = sender_auth(mail.auth_headers, mail.from_address)
    category = mail_category(mail.from_address, auth)
    if await uow.mail_messages.add(owner, mail, category, auth):
        report.stored += 1
    else:
        report.known += 1


async def _drop(
    uow: MailUnitOfWork,
    owner: UserId,
    mail: IncomingMail,
    reason: DropReason,
    report: SyncReport,
) -> None:
    """Відкинутий лист з відомим власником: причина, дата, відправник і тема — без тексту."""
    await uow.mail_dropped.add(owner, DroppedRecord.of(mail, reason))
    report.dropped.append(DroppedMail(mail.id, reason))
