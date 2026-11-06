"""Порти контексту mail: скринька застосунку (Gmail) і сховища пошти.

Лист скрізь — за id скриньки (`gmail_id`); власник — за tag особистої адреси. Скринька
лише читається.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from application.ports.applications import ApplicationRepository
from application.ports.jobs import JobRepository
from application.ports.profile import ProfileRepository
from application.ports.unit_of_work import UnitOfWork
from domain.identity.ids import UserId
from domain.mail.board import ReplyCounts, ReplyQuery
from domain.mail.inbox import (
    DroppedSummary,
    MailList,
    MailQuery,
    MailSummary,
    StoredMail,
)
from domain.mail.mail import (
    DroppedRecord,
    DropReason,
    IncomingMail,
    MailCategory,
    MailChanges,
    MailInbox,
    MailSyncState,
)
from domain.mail.replies import (
    AppliedJob,
    Reply,
    ReplyMail,
    ReplyMatch,
    ReplyType,
)
from domain.mail.sender_auth import SenderAuth


class Mailbox(Protocol):
    """Скринька застосунку. Збій — `MailboxError`, протухлий курсор — `CursorExpired`."""

    async def profile_cursor(self) -> str:
        """Поточний курсор змін скриньки."""
        ...

    async def changes(self, cursor: str) -> MailChanges:
        """Нові листи після курсора (у порядку надходження) і новий курсор."""
        ...

    async def since(self, moment: datetime) -> list[str]:
        """Id листів, що надійшли після моменту, від старіших до новіших."""
        ...

    async def message(self, message_id: str) -> IncomingMail | None:
        """Лист; None — зник зі скриньки."""
        ...


class MailInboxRepository(Protocol):
    async def ensure(self, user_id: UserId) -> MailInbox:
        """Особиста адреса користувача; нема — створює (tag випадковий)."""
        ...

    async def find(self, user_id: UserId) -> MailInbox | None:
        """Особиста адреса користувача; None — ще не створювалась (на відміну від `ensure`)."""
        ...

    async def owner(self, tag: str) -> UserId | None:
        """Власник чинного tag."""
        ...

    async def rotate(self, user_id: UserId) -> MailInbox:
        """Новий tag; старий переходить у колишні, листи на нього синк не зберігає."""
        ...

    async def retired_owner(self, tag: str) -> UserId | None:
        """Власник tag, що був до ротації."""
        ...


class MailMessageRepository(Protocol):
    async def known(self, gmail_ids: Sequence[str]) -> set[str]:
        """Які з цих листів уже збережені."""
        ...

    async def add(
        self,
        user_id: UserId,
        mail: IncomingMail,
        category: MailCategory,
        sender_auth: SenderAuth,
    ) -> bool:
        """Зберігає лист; False — такий уже є (повтор після збою, ресинк)."""
        ...

    async def count_received(
        self, user_id: UserId, after: datetime, until: datetime
    ) -> int:
        """Скільки листів користувача надійшло в (after, until]."""
        ...

    async def search(
        self, user_id: UserId, query: MailQuery, dropped_since: datetime
    ) -> MailList:
        """Рядки «Вхідних»: збережені листи й відкинуті з `dropped_since` (за фільтром виду
        і підрядком), новіші першими. `page.total` — скільки рядків усього."""
        ...

    async def recent(self, user_id: UserId, limit: int) -> list[MailSummary]:
        """Останні збережені листи (без відкинутих), новіші першими."""
        ...

    async def get(self, user_id: UserId, mail_id: int) -> StoredMail | None:
        """Лист із текстом; None — нема чи він чужий."""
        ...

    async def texts(self, user_id: UserId, mail_ids: Sequence[int]) -> dict[int, str]:
        """Тексти цих листів користувача (чужі й неіснуючі пропускаються)."""
        ...

    async def latest(
        self, user_id: UserId, category: MailCategory
    ) -> StoredMail | None:
        """Найновіший лист цієї категорії."""
        ...

    async def pending_alerts(self) -> list[tuple[int, UserId, str]]:
        """Листи linkedin_alert усіх користувачів, ще не розібрані у вакансії (id листа, власник,
        текст), старші першими."""
        ...

    async def mark_alerts_processed(
        self, mail_id: int, error: str, now: datetime
    ) -> None:
        """Лист розібрано: `now` — коли; непорожня `error` дописується до `parse_error`."""
        ...

    async def suspicious(self, user_id: UserId, since: datetime) -> DroppedSummary:
        """Скільки листів категорії suspicious надійшло після `since` і коли останній."""
        ...


class JobReplyRepository(Protocol):
    """Відповіді на подачі: зіставлення листа `company` з вакансією користувача (за номером) і
    розбір. Лист ідентифікується id у «Вхідних», відповідь — власним id."""

    async def pending(self) -> list[tuple[UserId, ReplyMail]]:
        """Листи `company` без зіставлення (усіх користувачів), старші першими."""
        ...

    async def thread_job(
        self, user_id: UserId, message_ids: Sequence[str]
    ) -> int | None:
        """Номер вакансії найновішої зіставленої відповіді користувача, чий лист має один
        із цих Message-ID."""
        ...

    async def add(
        self, user_id: UserId, mail_id: int, match: ReplyMatch, suggested: ReplyType
    ) -> None:
        """Записує зіставлення листа; повтор того самого листа не дублює."""
        ...

    async def applied(self, user_id: UserId) -> list[AppliedJob]:
        """Подані вакансії користувача, свіжіші подачі першими."""
        ...

    async def list(self, user_id: UserId, *, reviewed: bool, limit: int) -> list[Reply]:
        """Відповіді користувача: розібрані чи ні, новіші першими."""
        ...

    async def search(
        self, user_id: UserId, query: ReplyQuery
    ) -> tuple[Sequence[Reply], int]:
        """Сторінка черги за пошуком (компанія вакансії, відправник, тема, текст), новіші першими,
        і скільки відповідей у черзі за цим пошуком усього."""
        ...

    async def counts(self, user_id: UserId) -> ReplyCounts:
        """Скільки відповідей у кожній черзі (без пошуку)."""
        ...

    async def get(self, user_id: UserId, reply_id: int) -> Reply | None:
        """Відповідь; None — нема чи вона чужа."""
        ...

    async def review(
        self,
        user_id: UserId,
        reply_id: int,
        job_number: int | None,
        reply_type: ReplyType,
        reviewed_at: datetime,
    ) -> Reply:
        """Зберігає розбір (повторний замінює попередній); відповідь має існувати."""
        ...


class MailDroppedRepository(Protocol):
    async def known(self, gmail_ids: Sequence[str]) -> set[str]:
        """Які з цих листів уже відкинуті з відомим власником."""
        ...

    async def add(self, user_id: UserId, record: DroppedRecord) -> None:
        """Записує відкинутий лист; повтор того самого не дублює."""
        ...

    async def summary(
        self, user_id: UserId, reason: DropReason, since: datetime
    ) -> DroppedSummary:
        """Скільки листів відкинуто з цієї причини після `since` і коли надійшов останній."""
        ...


class MailSyncRepository(Protocol):
    async def lock(self) -> bool:
        """Бере лок синку до кінця транзакції; False — синк уже йде в іншому процесі."""
        ...

    async def get(self, mailbox: str) -> MailSyncState | None: ...

    async def save(self, mailbox: str, history_id: str, synced_at: datetime) -> None:
        """Новий курсор після успішного синку; помилку скидає."""
        ...

    async def fail(self, mailbox: str, error: str, failed_at: datetime) -> None:
        """Записує помилку синку; курсор не міняє."""
        ...


class MailSyncRequestRepository(Protocol):
    async def since(self, user_id: UserId, moment: datetime) -> list[datetime]:
        """Коли користувач запитував синк після `moment`."""
        ...

    async def add(self, user_id: UserId, requested_at: datetime) -> None: ...

    async def mark_handled(self, handled_at: datetime) -> int:
        """Позначає виконаними всі запити, що чекали; повертає скільки."""
        ...


class MailUnitOfWork(UnitOfWork, Protocol):
    @property
    def mail_inboxes(self) -> MailInboxRepository: ...

    @property
    def mail_messages(self) -> MailMessageRepository: ...

    @property
    def mail_dropped(self) -> MailDroppedRepository: ...

    @property
    def mail_sync(self) -> MailSyncRepository: ...

    @property
    def mail_sync_requests(self) -> MailSyncRequestRepository: ...

    @property
    def job_replies(self) -> JobReplyRepository: ...

    @property
    def jobs(self) -> JobRepository: ...

    @property
    def applications(self) -> ApplicationRepository: ...

    @property
    def profiles(self) -> ProfileRepository: ...
