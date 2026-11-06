"""In-memory адаптер пошти для core-тестів (та сама семантика, що в Postgres) і фейкова скринька."""

from collections.abc import Sequence
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime
from types import TracebackType
from typing import Self
from uuid import UUID

from domain.identity.ids import UserId
from domain.mail.board import ReplyCounts, ReplyQuery, ReplyQueue
from domain.mail.inbox import (
    DroppedSummary,
    MailKind,
    MailList,
    MailListItem,
    MailQuery,
    MailSummary,
    StoredMail,
)
from domain.mail.mail import (
    TAG_ALPHABET,
    CursorExpired,
    DroppedRecord,
    DropReason,
    IncomingMail,
    MailboxError,
    MailCategory,
    MailChanges,
    MailInbox,
    MailSyncState,
)
from domain.mail.replies import (
    AppliedJob,
    Confidence,
    MatchedBy,
    Reply,
    ReplyJob,
    ReplyMail,
    ReplyMatch,
    ReplyType,
)
from domain.mail.sender_auth import AuthHeaders, SenderAuth
from domain.profile.profile import Profile
from tests.support.jobs import InMemoryApplications, InMemoryJobs, Store
from tests.support.profile import InMemoryProfiles

ROTATED_AT = datetime(2026, 10, 5, 8, 0, tzinfo=UTC)


def auth_headers(from_address: str, dmarc: str = "pass") -> AuthHeaders:
    """Верхній Authentication-Results скриньки застосунку з вердиктом DMARC для домену From."""
    domain = from_address.rpartition("@")[2]
    return (
        (
            "authentication-results",
            f"mx.google.com; dmarc={dmarc} (p=NONE sp=NONE dis=NONE) header.from={domain}",
        ),
    )


@dataclass
class ReplyRecord:
    """Рядок `job_replies`: зіставлення листа (за номером у «Вхідних») з вакансією користувача."""

    user_id: UserId
    mail_number: int
    job_number: int | None
    confidence: Confidence | None
    matched_by: MatchedBy | None
    suggested_type: ReplyType
    type: ReplyType | None = None
    reviewed_at: datetime | None = None


@dataclass
class MailStore:
    inboxes: dict[UserId, MailInbox] = field(default_factory=dict)
    retired_tags: dict[str, UserId] = field(default_factory=dict)
    # gmail_id → (власник, лист, категорія, вердикт відправника)
    messages: dict[str, tuple[UserId, IncomingMail, MailCategory, SenderAuth]] = field(
        default_factory=dict
    )
    # gmail_id → (власник, запис без тексту)
    dropped: dict[str, tuple[UserId, DroppedRecord]] = field(default_factory=dict)
    sync: dict[str, MailSyncState] = field(default_factory=dict)
    # (користувач, коли запитано, коли виконано)
    sync_requests: list[tuple[UserId, datetime, datetime | None]] = field(
        default_factory=list
    )
    # Лок синку зайнятий іншим процесом.
    sync_busy: bool = False
    # Вакансії й подачі користувачів (одне сховище з контекстом jobs) і їхні профілі.
    jobs: Store = field(default_factory=Store.empty)
    profiles: dict[UserId, Profile] = field(default_factory=dict)
    # id відповіді → зіставлення листа.
    replies: dict[int, ReplyRecord] = field(default_factory=dict)
    # Номери листів linkedin_alert (у порядку збереження), які синк уже розібрав у вакансії.
    alerts_processed: dict[int, datetime] = field(default_factory=dict)

    def copy(self) -> Self:
        return type(self)(
            dict(self.inboxes),
            dict(self.retired_tags),
            dict(self.messages),
            dict(self.dropped),
            dict(self.sync),
            list(self.sync_requests),
            self.sync_busy,
            self.jobs.copy(),
            dict(self.profiles),
            {number: replace(record) for number, record in self.replies.items()},
            dict(self.alerts_processed),
        )


class InMemoryMailInboxes:
    def __init__(self, store: MailStore) -> None:
        self._s = store

    async def ensure(self, user_id: UserId) -> MailInbox:
        if user_id not in self._s.inboxes:
            # Теги за порядком створення: aaaaaaaaaaaa, bbbbbbbbbbbb, …
            letter = TAG_ALPHABET[len(self._s.inboxes) + len(self._s.retired_tags)]
            self._s.inboxes[user_id] = MailInbox(
                letter * 12, datetime(2026, 10, 1, tzinfo=UTC)
            )
        return self._s.inboxes[user_id]

    async def find(self, user_id: UserId) -> MailInbox | None:
        return self._s.inboxes.get(user_id)

    async def owner(self, tag: str) -> UserId | None:
        return next(
            (user for user, inbox in self._s.inboxes.items() if inbox.tag == tag),
            None,
        )

    async def rotate(self, user_id: UserId) -> MailInbox:
        old = await self.ensure(user_id)
        self._s.retired_tags.setdefault(old.tag, user_id)
        used = {inbox.tag for inbox in self._s.inboxes.values()}
        used |= set(self._s.retired_tags)
        fresh = next(c * 12 for c in TAG_ALPHABET if c * 12 not in used)
        self._s.inboxes[user_id] = replace(
            self._s.inboxes[user_id], tag=fresh, rotated_at=ROTATED_AT
        )
        return self._s.inboxes[user_id]

    async def retired_owner(self, tag: str) -> UserId | None:
        return self._s.retired_tags.get(tag)


class InMemoryMailMessages:
    def __init__(self, store: MailStore) -> None:
        self._s = store

    async def known(self, gmail_ids: Sequence[str]) -> set[str]:
        return set(gmail_ids) & set(self._s.messages)

    async def add(
        self,
        user_id: UserId,
        mail: IncomingMail,
        category: MailCategory,
        sender_auth: SenderAuth,
    ) -> bool:
        if mail.id in self._s.messages:
            return False
        self._s.messages[mail.id] = (user_id, mail, category, sender_auth)
        return True

    async def count_received(
        self, user_id: UserId, after: datetime, until: datetime
    ) -> int:
        return sum(
            1
            for owner, mail, _, _ in self._s.messages.values()
            if owner == user_id and after < mail.received_at <= until
        )

    def _summary(self, number: int) -> MailSummary:
        _, mail, category, auth = list(self._s.messages.values())[number - 1]
        return MailSummary(
            id=number,
            from_address=mail.from_address,
            from_name=mail.from_name,
            subject=mail.subject,
            category=category,
            received_at=mail.received_at,
            sender_auth=auth,
        )

    def _mine(self, user_id: UserId) -> list[int]:
        return [
            number
            for number, (owner, _, _, _) in enumerate(
                self._s.messages.values(), start=1
            )
            if owner == user_id
        ]

    async def search(
        self, user_id: UserId, query: MailQuery, dropped_since: datetime
    ) -> MailList:
        needle = query.text.casefold()
        items: list[MailListItem] = []
        if query.kind is not MailKind.DROPPED:
            for number in self._mine(user_id):
                _, mail, category, auth = list(self._s.messages.values())[number - 1]
                if query.kind is not None and category not in query.kind.categories:
                    continue
                haystack = (
                    mail.from_address,
                    mail.from_name,
                    mail.subject,
                    mail.text,
                )
                if needle and not any(needle in part.casefold() for part in haystack):
                    continue
                items.append(
                    MailListItem(
                        id=number,
                        dropped=False,
                        from_address=mail.from_address,
                        from_name=mail.from_name,
                        subject=mail.subject,
                        received_at=mail.received_at,
                        category=category,
                        sender_auth=auth,
                    )
                )
        if query.kind in (None, MailKind.DROPPED):
            for number, (owner, record) in enumerate(self._s.dropped.values(), start=1):
                if owner != user_id or record.received_at <= dropped_since:
                    continue
                dropped_fields = (record.from_address, record.subject)
                if needle and not any(
                    needle in part.casefold() for part in dropped_fields
                ):
                    continue
                items.append(
                    MailListItem(
                        id=number,
                        dropped=True,
                        from_address=record.from_address,
                        from_name="",
                        subject=record.subject,
                        received_at=record.received_at,
                        reason=record.reason,
                    )
                )
        items.sort(key=lambda i: (i.received_at, not i.dropped, i.id), reverse=True)
        page = replace(query.page, total=len(items))
        return MailList(tuple(items[page.offset : page.offset + page.size]), page)

    async def recent(self, user_id: UserId, limit: int) -> list[MailSummary]:
        found = [self._summary(number) for number in self._mine(user_id)]
        found.sort(key=lambda m: (m.received_at, m.id), reverse=True)
        return found[:limit]

    async def get(self, user_id: UserId, mail_id: int) -> StoredMail | None:
        if mail_id not in self._mine(user_id):
            return None
        mail = list(self._s.messages.values())[mail_id - 1][1]
        return StoredMail(self._summary(mail_id), mail.text)

    async def texts(self, user_id: UserId, mail_ids: Sequence[int]) -> dict[int, str]:
        mine = set(self._mine(user_id))
        return {
            number: list(self._s.messages.values())[number - 1][1].text
            for number in mail_ids
            if number in mine
        }

    async def latest(
        self, user_id: UserId, category: MailCategory
    ) -> StoredMail | None:
        found = [
            summary
            for summary in (self._summary(n) for n in self._mine(user_id))
            if summary.category is category
        ]
        if not found:
            return None
        newest = max(found, key=lambda m: (m.received_at, m.id))
        return StoredMail(
            newest, list(self._s.messages.values())[newest.id - 1][1].text
        )

    async def suspicious(self, user_id: UserId, since: datetime) -> DroppedSummary:
        times = [
            s.received_at
            for s in (self._summary(n) for n in self._mine(user_id))
            if s.category is MailCategory.SUSPICIOUS and s.received_at >= since
        ]
        return DroppedSummary(len(times), max(times, default=None))

    async def pending_alerts(self) -> list[tuple[int, UserId, str]]:
        found = [
            (number, owner, mail)
            for number, (owner, mail, category, _) in enumerate(
                self._s.messages.values(), start=1
            )
            if category is MailCategory.LINKEDIN_ALERT
            and number not in self._s.alerts_processed
        ]
        found.sort(key=lambda item: (item[2].received_at, item[0]))
        return [(number, owner, mail.text) for number, owner, mail in found]

    async def mark_alerts_processed(
        self, mail_id: int, error: str, now: datetime
    ) -> None:
        gmail_id = list(self._s.messages)[mail_id - 1]
        owner, mail, category, auth = self._s.messages[gmail_id]
        problems = "; ".join(part for part in (mail.parse_error, error) if part)
        self._s.messages[gmail_id] = (
            owner,
            replace(mail, parse_error=problems),
            category,
            auth,
        )
        self._s.alerts_processed[mail_id] = now


def _queue_of(reply: Reply) -> ReplyQueue:
    if reply.reviewed_at is not None:
        return ReplyQueue.REVIEWED
    return ReplyQueue.UNMATCHED if reply.job is None else ReplyQueue.MATCHED


class InMemoryJobReplies:
    def __init__(self, store: MailStore) -> None:
        self._s = store
        self._mail = InMemoryMailMessages(store)

    async def pending(self) -> list[tuple[UserId, ReplyMail]]:
        done = {record.mail_number for record in self._s.replies.values()}
        found: list[tuple[UserId, ReplyMail]] = []
        for number, (owner, mail, category, auth) in enumerate(
            self._s.messages.values(), start=1
        ):
            if category is MailCategory.COMPANY and number not in done:
                found.append(
                    (
                        owner,
                        ReplyMail(
                            id=number,
                            received_at=mail.received_at,
                            message_id=mail.message_id,
                            in_reply_to=mail.in_reply_to,
                            references=mail.references,
                            from_address=mail.from_address,
                            from_name=mail.from_name,
                            subject=mail.subject,
                            text=mail.text,
                            sender_auth=auth,
                        ),
                    )
                )
        found.sort(key=lambda item: (item[1].received_at, item[1].id))
        return found

    async def thread_job(
        self, user_id: UserId, message_ids: Sequence[str]
    ) -> int | None:
        if not message_ids:
            return None
        messages = list(self._s.messages.values())
        for _, record in sorted(self._s.replies.items(), reverse=True):
            if (
                record.user_id == user_id
                and record.job_number is not None
                and messages[record.mail_number - 1][1].message_id in message_ids
            ):
                return record.job_number
        return None

    async def add(
        self, user_id: UserId, mail_id: int, match: ReplyMatch, suggested: ReplyType
    ) -> None:
        if any(record.mail_number == mail_id for record in self._s.replies.values()):
            return
        self._s.replies[max(self._s.replies, default=0) + 1] = ReplyRecord(
            user_id,
            mail_id,
            match.job_number,
            match.confidence,
            match.matched_by,
            suggested,
        )

    async def applied(self, user_id: UserId) -> list[AppliedJob]:
        found = [
            (application, self._s.jobs.jobs[(owner, number)])
            for (owner, number), application in self._s.jobs.applications.items()
            if owner == user_id
        ]
        found.sort(
            key=lambda item: (item[0].applied_on, item[0].job_number), reverse=True
        )
        return [
            AppliedJob(
                job_number=application.job_number,
                title=job.title,
                company=job.company,
                status=application.status,
                ats=application.ats,
                company_domains=application.company_domains,
                company_emails=application.company_emails,
            )
            for application, job in found
        ]

    def _reply(self, reply_id: int) -> Reply:
        record = self._s.replies[reply_id]
        mail_id = record.mail_number
        key = None if record.job_number is None else (record.user_id, record.job_number)
        job = None if key is None else self._s.jobs.jobs.get(key)
        application = None if key is None else self._s.jobs.applications.get(key)
        return Reply(
            id=reply_id,
            mail=self._mail._summary(mail_id),
            text=list(self._s.messages.values())[mail_id - 1][1].text,
            job=None
            if job is None or record.job_number is None
            else ReplyJob(
                record.job_number,
                job.title,
                job.company,
                None if application is None else application.status,
            ),
            confidence=record.confidence,
            matched_by=record.matched_by,
            suggested_type=record.suggested_type,
            type=record.type,
            reviewed_at=record.reviewed_at,
        )

    async def list(self, user_id: UserId, *, reviewed: bool, limit: int) -> list[Reply]:
        found = [
            self._reply(reply_id)
            for reply_id, record in self._s.replies.items()
            if record.user_id == user_id
            and (record.reviewed_at is not None) == reviewed
        ]
        found.sort(key=lambda r: (r.mail.received_at, r.id), reverse=True)
        return found[:limit]

    async def search(
        self, user_id: UserId, query: ReplyQuery
    ) -> tuple[Sequence[Reply], int]:
        needle = query.text.casefold()
        found: list[Reply] = []
        for reply_id, record in self._s.replies.items():
            if record.user_id != user_id:
                continue
            reply = self._reply(reply_id)
            if _queue_of(reply) is not query.queue:
                continue
            haystack = (
                "" if reply.job is None else reply.job.company or "",
                reply.mail.from_name,
                reply.mail.from_address,
                reply.mail.subject,
                reply.text,
            )
            if needle and not any(needle in part.casefold() for part in haystack):
                continue
            found.append(reply)
        found.sort(key=lambda r: (r.mail.received_at, r.id), reverse=True)
        page = query.page
        return found[page.offset : page.offset + page.size], len(found)

    async def counts(self, user_id: UserId) -> ReplyCounts:
        queues = [
            _queue_of(self._reply(reply_id))
            for reply_id, record in self._s.replies.items()
            if record.user_id == user_id
        ]
        return ReplyCounts(
            matched=queues.count(ReplyQueue.MATCHED),
            unmatched=queues.count(ReplyQueue.UNMATCHED),
            reviewed=queues.count(ReplyQueue.REVIEWED),
        )

    async def get(self, user_id: UserId, reply_id: int) -> Reply | None:
        record = self._s.replies.get(reply_id)
        if record is None or record.user_id != user_id:
            return None
        return self._reply(reply_id)

    async def review(
        self,
        user_id: UserId,
        reply_id: int,
        job_number: int | None,
        reply_type: ReplyType,
        reviewed_at: datetime,
    ) -> Reply:
        record = self._s.replies[reply_id]
        assert record.user_id == user_id
        record.job_number = job_number
        record.type = reply_type
        record.reviewed_at = reviewed_at
        return self._reply(reply_id)


class InMemoryMailDropped:
    def __init__(self, store: MailStore) -> None:
        self._s = store

    async def known(self, gmail_ids: Sequence[str]) -> set[str]:
        return set(gmail_ids) & set(self._s.dropped)

    async def add(self, user_id: UserId, record: DroppedRecord) -> None:
        self._s.dropped.setdefault(record.gmail_id, (user_id, record))

    async def summary(
        self, user_id: UserId, reason: DropReason, since: datetime
    ) -> DroppedSummary:
        times = [
            record.received_at
            for owner, record in self._s.dropped.values()
            if owner == user_id
            and record.reason is reason
            and record.received_at > since
        ]
        return DroppedSummary(len(times), max(times, default=None))


class InMemoryMailSync:
    def __init__(self, store: MailStore) -> None:
        self._s = store

    async def lock(self) -> bool:
        return not self._s.sync_busy

    async def get(self, mailbox: str) -> MailSyncState | None:
        return self._s.sync.get(mailbox)

    async def save(self, mailbox: str, history_id: str, synced_at: datetime) -> None:
        current = self._s.sync.get(mailbox, MailSyncState())
        self._s.sync[mailbox] = replace(
            current, history_id=history_id, synced_at=synced_at, last_error=""
        )

    async def fail(self, mailbox: str, error: str, failed_at: datetime) -> None:
        current = self._s.sync.get(mailbox, MailSyncState())
        self._s.sync[mailbox] = replace(current, last_error=error, failed_at=failed_at)


class InMemoryMailSyncRequests:
    def __init__(self, store: MailStore) -> None:
        self._s = store

    async def since(self, user_id: UserId, moment: datetime) -> list[datetime]:
        return [
            at
            for owner, at, _ in self._s.sync_requests
            if owner == user_id and at > moment
        ]

    async def add(self, user_id: UserId, requested_at: datetime) -> None:
        self._s.sync_requests.append((user_id, requested_at, None))

    async def mark_handled(self, handled_at: datetime) -> int:
        pending = [
            i for i, (_, _, done) in enumerate(self._s.sync_requests) if done is None
        ]
        for i in pending:
            owner, at, _ = self._s.sync_requests[i]
            self._s.sync_requests[i] = (owner, at, handled_at)
        return len(pending)


class InMemoryMailUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(self, store: MailStore) -> None:
        self._store = store
        self._staged: MailStore | None = None

    def _state(self) -> MailStore:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged

    @property
    def mail_inboxes(self) -> InMemoryMailInboxes:
        return InMemoryMailInboxes(self._state())

    @property
    def mail_messages(self) -> InMemoryMailMessages:
        return InMemoryMailMessages(self._state())

    @property
    def mail_dropped(self) -> InMemoryMailDropped:
        return InMemoryMailDropped(self._state())

    @property
    def mail_sync(self) -> InMemoryMailSync:
        return InMemoryMailSync(self._state())

    @property
    def mail_sync_requests(self) -> InMemoryMailSyncRequests:
        return InMemoryMailSyncRequests(self._state())

    @property
    def job_replies(self) -> InMemoryJobReplies:
        return InMemoryJobReplies(self._state())

    @property
    def jobs(self) -> InMemoryJobs:
        return InMemoryJobs(self._state().jobs)

    @property
    def applications(self) -> InMemoryApplications:
        return InMemoryApplications(self._state().jobs)

    @property
    def profiles(self) -> InMemoryProfiles:
        return InMemoryProfiles(self._state().profiles, {})

    async def __aenter__(self) -> Self:
        self._staged = self._store.copy()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        staged = self._state()
        self._store.inboxes = staged.inboxes
        self._store.retired_tags = staged.retired_tags
        self._store.messages = staged.messages
        self._store.dropped = staged.dropped
        self._store.sync = staged.sync
        self._store.sync_requests = staged.sync_requests
        self._store.replies = staged.replies
        self._store.alerts_processed = staged.alerts_processed
        for item in fields(Store):
            setattr(self._store.jobs, item.name, getattr(staged.jobs, item.name))
        self._store.profiles.clear()
        self._store.profiles.update(staged.profiles)


@dataclass
class FakeMailbox:
    """Скринька застосунку в пам'яті: курсор — лічильник, кожен новий лист його збільшує."""

    cursor: int = 100
    mails: dict[str, IncomingMail] = field(default_factory=dict)
    # (курсор після листа, id листа)
    history: list[tuple[int, str]] = field(default_factory=list)
    # Курсори, менші за цей, протухли.
    expired_before: int = 0
    # Листи, що є в змінах, але зникли до читання.
    gone: set[str] = field(default_factory=set)
    # Якщо задано — кожен виклик падає з цією помилкою.
    error: MailboxError | None = None
    since_calls: list[datetime] = field(default_factory=list)
    fetched: list[str] = field(default_factory=list)

    def deliver(self, *mails: IncomingMail) -> None:
        for mail in mails:
            self.cursor += 1
            self.mails[mail.id] = mail
            self.history.append((self.cursor, mail.id))

    async def profile_cursor(self) -> str:
        self._check()
        return str(self.cursor)

    async def changes(self, cursor: str) -> MailChanges:
        self._check()
        if int(cursor) < self.expired_before:
            raise CursorExpired("протух")
        ids = tuple(gmail_id for at, gmail_id in self.history if at > int(cursor))
        return MailChanges(ids, str(self.cursor))

    async def since(self, moment: datetime) -> list[str]:
        self._check()
        self.since_calls.append(moment)
        return [m.id for m in self.mails.values() if m.received_at > moment]

    async def message(self, message_id: str) -> IncomingMail | None:
        self._check()
        self.fetched.append(message_id)
        return None if message_id in self.gone else self.mails.get(message_id)

    def _check(self) -> None:
        if self.error is not None:
            raise self.error


def user(number: int) -> UserId:
    return UserId(UUID(int=number))
