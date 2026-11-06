"""Пошта користувача: особиста адреса для пересилання, її ротація, «Вхідні» (збережені й
відкинуті листи, пошук, фільтр виду, сторінки), читалка з кодом пересилання Gmail, синк
вручну. Текст, відправник і тема листів — недовірені дані; чужої пошти тут не видно."""

from collections.abc import Callable, Sequence

from application.contracts.actor import Actor
from application.contracts.mail import (
    ForwardingData,
    MailDetailData,
    MailInboxData,
    MailSettingsData,
)
from application.ports.clock import Clock
from application.ports.mail import MailUnitOfWork
from domain.identity.ids import UserId
from domain.mail.forwarded import ForwardedMail, manual_forward
from domain.mail.inbox import (
    DROPPED_NOTICE_WINDOW,
    MANUAL_SYNC_WINDOW,
    RECENT_MAIL_LIMIT,
    MailList,
    MailNotConfigured,
    MailQuery,
    MailSummary,
    ManualSync,
    ManualSyncLimit,
    StoredMail,
    display_text,
    manual_sync,
)
from domain.mail.mail import (
    DropReason,
    MailCategory,
    MailInbox,
    forwarding_request,
    personal_address,
)
from domain.shared.errors import NotFound


class MailUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], MailUnitOfWork],
        clock: Clock,
        mailbox: str,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._mailbox = mailbox

    async def settings(self, actor: Actor) -> MailSettingsData:
        """Адреса для пересилання, стан синку й ліміт синку вручну. `MailNotConfigured` —
        нема адреси скриньки застосунку."""
        self._check_mailbox()
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            inbox = await uow.mail_inboxes.ensure(actor.user_id)
            sync = await uow.mail_sync.get(self._mailbox.lower())
            requested = await uow.mail_sync_requests.since(
                actor.user_id, now - MANUAL_SYNC_WINDOW
            )
            await uow.commit()
        return MailSettingsData(
            address=personal_address(self._mailbox, inbox.tag),
            rotated_at=inbox.rotated_at,
            synced_at=None if sync is None else sync.synced_at,
            sync_failed=sync is not None and bool(sync.last_error),
            sync_error="" if sync is None else sync.last_error,
            manual=manual_sync(requested, now),
        )

    async def rotate_address(self, actor: Actor) -> str:
        """Нова особиста адреса; листи на стару синк більше не зберігає, а записує. Повертає її."""
        self._check_mailbox()
        async with self._unit_of_work() as uow:
            inbox = await uow.mail_inboxes.rotate(actor.user_id)
            await uow.commit()
        return personal_address(self._mailbox, inbox.tag)

    async def request_sync(self, actor: Actor) -> ManualSync:
        """Запит синку вручну: записується в БД, процес синку виконує його. Ліміт —
        `ManualSyncLimit`."""
        self._check_mailbox()
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            requested = await uow.mail_sync_requests.since(
                actor.user_id, now - MANUAL_SYNC_WINDOW
            )
            state = manual_sync(requested, now)
            if state.next_at is not None:
                raise ManualSyncLimit(state.next_at)
            await uow.mail_sync_requests.add(actor.user_id, now)
            await uow.commit()
        return manual_sync([*requested, now], now)

    async def list_mail(self, actor: Actor, query: MailQuery) -> MailList:
        """«Вхідні»: збережені листи й відкинуті за 30 днів, за пошуком і видом, сторінкою."""
        self._check_mailbox()
        since = self._clock.now() - DROPPED_NOTICE_WINDOW
        async with self._unit_of_work() as uow:
            return await uow.mail_messages.search(actor.user_id, query, since)

    async def get_mail(self, actor: Actor, mail_id: int) -> MailDetailData:
        """Лист з текстом; для підтвердження пересилання — ще й код. `NotFound` — листа нема
        чи він чужий."""
        self._check_mailbox()
        async with self._unit_of_work() as uow:
            found = await uow.mail_messages.get(actor.user_id, mail_id)
            if found is None:
                raise NotFound(f"Листа {mail_id} не знайдено.")
            inbox = await uow.mail_inboxes.ensure(actor.user_id)
            await uow.commit()
        forwarding = None
        if found.summary.category is MailCategory.FORWARDING_CONFIRMATION:
            forwarding = self._forwarding(found, inbox)
        return MailDetailData(
            mail=found.summary, text=display_text(found.text), forwarding=forwarding
        )

    async def inbox_overview(self, actor: Actor) -> MailInboxData:
        """Огляд для MCP: адреса, код пересилання, останні 20 листів, стан синку, лічильники."""
        self._check_mailbox()
        now = self._clock.now()
        since = now - DROPPED_NOTICE_WINDOW
        user_id: UserId = actor.user_id
        async with self._unit_of_work() as uow:
            inbox = await uow.mail_inboxes.ensure(user_id)
            recent = await uow.mail_messages.recent(user_id, RECENT_MAIL_LIMIT)
            latest = await uow.mail_messages.latest(
                user_id, MailCategory.FORWARDING_CONFIRMATION
            )
            sync = await uow.mail_sync.get(self._mailbox.lower())
            limit_drops = await uow.mail_dropped.summary(
                user_id, DropReason.DAILY_LIMIT, since
            )
            old_address_drops = await uow.mail_dropped.summary(
                user_id, DropReason.RETIRED_TAG, since
            )
            suspicious = await uow.mail_messages.suspicious(user_id, since)
            email = (await uow.profiles.get(user_id)).contacts.email
            forwarded = await self._forwarded(uow, user_id, recent, email)
            await uow.commit()
        forwarding = None if latest is None else self._forwarding(latest, inbox)
        return MailInboxData(
            address=personal_address(self._mailbox, inbox.tag),
            # Код до ротації — для старої адреси: Gmail надішле новий на нову.
            forwarding=forwarding if forwarding and forwarding.current else None,
            recent=tuple(recent),
            synced_at=None if sync is None else sync.synced_at,
            sync_failed=sync is not None and bool(sync.last_error),
            limit_drops=limit_drops,
            old_address_drops=old_address_drops,
            suspicious=suspicious,
            forwarded=forwarded,
        )

    async def _forwarded(
        self,
        uow: MailUnitOfWork,
        user_id: UserId,
        recent: Sequence[MailSummary],
        email: str,
    ) -> dict[int, ForwardedMail]:
        """Листи з `recent`, які власник переслав вручну, за id листа. Текст читається лише
        для листів з його власної адреси."""
        own = email.strip().lower()
        ids = [m.id for m in recent if own and m.from_address.lower() == own]
        texts = await uow.mail_messages.texts(user_id, ids)
        return {
            mail.id: found
            for mail in recent
            if mail.id in texts
            and (
                found := manual_forward(
                    email, mail.from_address, mail.sender_auth, texts[mail.id]
                )
            )
            is not None
        }

    def _check_mailbox(self) -> None:
        if not self._mailbox:
            raise MailNotConfigured

    def _forwarding(self, mail: StoredMail, inbox: MailInbox) -> ForwardingData:
        summary = mail.summary
        request = forwarding_request(
            summary.subject,
            mail.text,
            summary.received_at,
            personal_address(self._mailbox, inbox.tag),
        )
        return ForwardingData(
            code=request.code,
            requested_by=request.requested_by,
            received_at=request.received_at,
            current=inbox.rotated_at is None or summary.received_at >= inbox.rotated_at,
        )
