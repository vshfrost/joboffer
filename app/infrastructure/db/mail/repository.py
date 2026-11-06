"""Репозиторії пошти на Postgres (AsyncSession одного UoW).

Власник листа — за tag особистої адреси; лист ідентифікується id скриньки (`gmail_id`), тож
повторне збереження того самого нічого не дублює. Синк скриньки один на базу: лок — pg advisory
на час транзакції.
"""

import secrets
from collections.abc import Sequence
from dataclasses import asdict, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Select,
    Text,
    cast,
    func,
    literal,
    null,
    or_,
    select,
    union_all,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.identity.ids import UserId
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
    TAG_LENGTH,
    DroppedRecord,
    DropReason,
    IncomingMail,
    MailCategory,
    MailInbox,
    MailSyncState,
)
from domain.mail.sender_auth import SenderAuth
from infrastructure.db.mail.tables import (
    MailDroppedRow,
    MailInboxRow,
    MailMessageRow,
    MailRetiredTagRow,
    MailSendRow,
    MailSyncRequestRow,
    MailSyncStateRow,
)

# Ключ pg advisory lock синку пошти: один синк на базу.
SYNC_LOCK_KEY = 0x6A6F626F66666572  # «joboffer» в ASCII


def new_tag() -> str:
    return "".join(secrets.choice(TAG_ALPHABET) for _ in range(TAG_LENGTH))


class PostgresMailInboxes:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure(self, user_id: UserId) -> MailInbox:
        # Два перші запити одночасно: другий INSERT нічого не робить, обидва читають той самий.
        await self._session.execute(
            pg_insert(MailInboxRow)
            .values(user_id=user_id.value, tag=new_tag())
            .on_conflict_do_nothing(index_elements=[MailInboxRow.user_id])
        )
        row = (
            await self._session.execute(
                select(MailInboxRow)
                .where(MailInboxRow.user_id == user_id.value)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        return MailInbox(row.tag, row.created_at, row.rotated_at)

    async def find(self, user_id: UserId) -> MailInbox | None:
        row = (
            await self._session.execute(
                select(MailInboxRow)
                .where(MailInboxRow.user_id == user_id.value)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        return (
            None if row is None else MailInbox(row.tag, row.created_at, row.rotated_at)
        )

    async def owner(self, tag: str) -> UserId | None:
        found = (
            await self._session.execute(
                select(MailInboxRow.user_id).where(MailInboxRow.tag == tag)
            )
        ).scalar_one_or_none()
        return None if found is None else UserId(found)

    async def rotate(self, user_id: UserId) -> MailInbox:
        old = await self.ensure(user_id)
        await self._session.execute(
            pg_insert(MailRetiredTagRow)
            .values(tag=old.tag, user_id=user_id.value)
            .on_conflict_do_nothing(index_elements=[MailRetiredTagRow.tag])
        )
        await self._session.execute(
            update(MailInboxRow)
            .where(MailInboxRow.user_id == user_id.value)
            .values(tag=new_tag(), rotated_at=func.now())
        )
        return await self.ensure(user_id)

    async def retired_owner(self, tag: str) -> UserId | None:
        found: UUID | None = (
            await self._session.execute(
                select(MailRetiredTagRow.user_id).where(MailRetiredTagRow.tag == tag)
            )
        ).scalar_one_or_none()
        return None if found is None else UserId(found)


class PostgresMailMessages:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def known(self, gmail_ids: Sequence[str]) -> set[str]:
        if not gmail_ids:
            return set()
        found = await self._session.execute(
            select(MailMessageRow.gmail_id).where(
                MailMessageRow.gmail_id.in_(gmail_ids)
            )
        )
        return set(found.scalars())

    async def add(
        self,
        user_id: UserId,
        mail: IncomingMail,
        category: MailCategory,
        sender_auth: SenderAuth,
    ) -> bool:
        added = (
            await self._session.execute(
                pg_insert(MailMessageRow)
                .values(
                    user_id=user_id.value,
                    gmail_id=mail.id,
                    message_id=mail.message_id,
                    in_reply_to=mail.in_reply_to,
                    reference_ids=list(mail.references),
                    from_address=mail.from_address,
                    from_name=mail.from_name,
                    to_addresses=list(mail.to),
                    subject=mail.subject,
                    sent_at=mail.sent_at,
                    received_at=mail.received_at,
                    category=category.value,
                    sender_auth=sender_auth.value,
                    untrusted_text=mail.text,
                    attachments=[asdict(item) for item in mail.attachments],
                    parse_error=mail.parse_error,
                )
                .on_conflict_do_nothing(index_elements=[MailMessageRow.gmail_id])
                .returning(MailMessageRow.id)
            )
        ).scalar_one_or_none()
        return added is not None

    async def count_received(
        self, user_id: UserId, after: datetime, until: datetime
    ) -> int:
        return (
            await self._session.execute(
                select(func.count()).where(
                    MailMessageRow.user_id == user_id.value,
                    MailMessageRow.received_at > after,
                    MailMessageRow.received_at <= until,
                )
            )
        ).scalar_one()

    async def search(
        self, user_id: UserId, query: MailQuery, dropped_since: datetime
    ) -> MailList:
        parts: list[Select[*tuple[Any, ...]]] = []
        if query.kind is not MailKind.DROPPED:
            parts.append(_stored_rows(user_id, query))
        if query.kind in (None, MailKind.DROPPED):
            parts.append(_dropped_rows(user_id, query, dropped_since))
        rows = (parts[0] if len(parts) == 1 else union_all(*parts)).subquery()
        total = (
            await self._session.execute(select(func.count()).select_from(rows))
        ).scalar_one()
        page = replace(query.page, total=total)
        found = await self._session.execute(
            select(rows)
            .order_by(rows.c.received_at.desc(), rows.c.dropped.asc(), rows.c.id.desc())
            .limit(page.size)
            .offset(page.offset)
        )
        items = tuple(
            MailListItem(
                id=row.id,
                dropped=row.dropped,
                from_address=row.from_address,
                from_name=row.from_name,
                subject=row.subject,
                received_at=row.received_at,
                category=None if row.category is None else MailCategory(row.category),
                sender_auth=None
                if row.sender_auth is None
                else SenderAuth(row.sender_auth),
                reason=None if row.reason is None else DropReason(row.reason),
            )
            for row in found
        )
        return MailList(items, page)

    async def recent(self, user_id: UserId, limit: int) -> list[MailSummary]:
        found = await self._session.execute(
            select(MailMessageRow)
            .where(MailMessageRow.user_id == user_id.value)
            .order_by(MailMessageRow.received_at.desc(), MailMessageRow.id.desc())
            .limit(limit)
        )
        return [_summary(row) for row in found.scalars()]

    async def get(self, user_id: UserId, mail_id: int) -> StoredMail | None:
        if not 1 <= mail_id <= MAX_MAIL_ID:
            return None
        row = (
            await self._session.execute(
                select(MailMessageRow).where(
                    MailMessageRow.user_id == user_id.value,
                    MailMessageRow.id == mail_id,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else StoredMail(_summary(row), row.untrusted_text)

    async def texts(self, user_id: UserId, mail_ids: Sequence[int]) -> dict[int, str]:
        if not mail_ids:
            return {}
        found = await self._session.execute(
            select(MailMessageRow.id, MailMessageRow.untrusted_text).where(
                MailMessageRow.user_id == user_id.value,
                MailMessageRow.id.in_(mail_ids),
            )
        )
        return dict(found.all())

    async def latest(
        self, user_id: UserId, category: MailCategory
    ) -> StoredMail | None:
        row = (
            await self._session.execute(
                select(MailMessageRow)
                .where(
                    MailMessageRow.user_id == user_id.value,
                    MailMessageRow.category == category.value,
                )
                .order_by(MailMessageRow.received_at.desc(), MailMessageRow.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return None if row is None else StoredMail(_summary(row), row.untrusted_text)

    async def pending_alerts(self) -> list[tuple[int, UserId, str]]:
        found = await self._session.execute(
            select(
                MailMessageRow.id, MailMessageRow.user_id, MailMessageRow.untrusted_text
            )
            .where(
                MailMessageRow.category == MailCategory.LINKEDIN_ALERT.value,
                MailMessageRow.alerts_processed_at.is_(None),
            )
            .order_by(MailMessageRow.received_at, MailMessageRow.id)
        )
        return [(mail_id, UserId(owner), text) for mail_id, owner, text in found]

    async def mark_alerts_processed(
        self, mail_id: int, error: str, now: datetime
    ) -> None:
        await self._session.execute(
            update(MailMessageRow)
            .where(MailMessageRow.id == mail_id)
            .values(
                alerts_processed_at=now,
                parse_error=func.concat_ws(
                    "; ",
                    func.nullif(MailMessageRow.parse_error, ""),
                    literal(error or None, Text),
                ),
            )
        )

    async def suspicious(self, user_id: UserId, since: datetime) -> DroppedSummary:
        count, last_at = (
            await self._session.execute(
                select(func.count(), func.max(MailMessageRow.received_at)).where(
                    MailMessageRow.user_id == user_id.value,
                    MailMessageRow.category == MailCategory.SUSPICIOUS.value,
                    MailMessageRow.received_at >= since,
                )
            )
        ).one()
        return DroppedSummary(count, last_at)


class PostgresMailDropped:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def known(self, gmail_ids: Sequence[str]) -> set[str]:
        if not gmail_ids:
            return set()
        found = await self._session.execute(
            select(MailDroppedRow.gmail_id).where(
                MailDroppedRow.gmail_id.in_(gmail_ids)
            )
        )
        return set(found.scalars())

    async def add(self, user_id: UserId, record: DroppedRecord) -> None:
        await self._session.execute(
            pg_insert(MailDroppedRow)
            .values(
                user_id=user_id.value,
                gmail_id=record.gmail_id,
                reason=record.reason.value,
                received_at=record.received_at,
                from_address=record.from_address,
                subject=record.subject,
            )
            .on_conflict_do_nothing(index_elements=[MailDroppedRow.gmail_id])
        )

    async def summary(
        self, user_id: UserId, reason: DropReason, since: datetime
    ) -> DroppedSummary:
        count, last_at = (
            await self._session.execute(
                select(func.count(), func.max(MailDroppedRow.received_at)).where(
                    MailDroppedRow.user_id == user_id.value,
                    MailDroppedRow.reason == reason.value,
                    MailDroppedRow.received_at > since,
                )
            )
        ).one()
        return DroppedSummary(count, last_at)


class PostgresMailSync:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self) -> bool:
        # Транзакційне: відпускається з commit / rollback, навіть якщо процес упав.
        locked: bool = (
            await self._session.execute(
                select(func.pg_try_advisory_xact_lock(SYNC_LOCK_KEY))
            )
        ).scalar_one()
        return locked

    async def get(self, mailbox: str) -> MailSyncState | None:
        row = await self._session.get(MailSyncStateRow, mailbox, populate_existing=True)
        if row is None:
            return None
        return MailSyncState(
            history_id=row.history_id,
            synced_at=row.synced_at,
            last_error=row.last_error,
            failed_at=row.failed_at,
        )

    async def save(self, mailbox: str, history_id: str, synced_at: datetime) -> None:
        await self._upsert(
            mailbox,
            {"history_id": history_id, "synced_at": synced_at, "last_error": ""},
        )

    async def fail(self, mailbox: str, error: str, failed_at: datetime) -> None:
        await self._upsert(mailbox, {"last_error": error, "failed_at": failed_at})

    async def _upsert(self, mailbox: str, values: dict[str, object]) -> None:
        await self._session.execute(
            pg_insert(MailSyncStateRow)
            .values(mailbox=mailbox, **values)
            .on_conflict_do_update(
                index_elements=[MailSyncStateRow.mailbox], set_=values
            )
        )


class PostgresMailSyncRequests:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def since(self, user_id: UserId, moment: datetime) -> list[datetime]:
        found = await self._session.execute(
            select(MailSyncRequestRow.requested_at).where(
                MailSyncRequestRow.user_id == user_id.value,
                MailSyncRequestRow.requested_at > moment,
            )
        )
        return list(found.scalars())

    async def add(self, user_id: UserId, requested_at: datetime) -> None:
        self._session.add(
            MailSyncRequestRow(user_id=user_id.value, requested_at=requested_at)
        )

    async def mark_handled(self, handled_at: datetime) -> int:
        done = await self._session.execute(
            update(MailSyncRequestRow)
            .where(MailSyncRequestRow.handled_at.is_(None))
            .values(handled_at=handled_at)
        )
        return int(done.rowcount)  # type: ignore[attr-defined]


# Найбільший id листа (BIGINT): більший за нього не існує, і запит не доходить до бази.
MAX_MAIL_ID = 2**63 - 1


def _escape_like(needle: str) -> str:
    return needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def matches(needle: str, *columns: Any) -> list[Any]:
    """Підрядок без урахування регістру; `%` і `_` у запиті — звичайні символи."""
    if not needle:
        return []
    pattern = f"%{_escape_like(needle)}%"
    return [or_(*(column.ilike(pattern, escape="\\") for column in columns))]


def _stored_rows(user_id: UserId, query: MailQuery) -> Select[*tuple[Any, ...]]:
    row = MailMessageRow
    filters = [row.user_id == user_id.value]
    if query.kind is not None:
        filters.append(row.category.in_([c.value for c in query.kind.categories]))
    filters += matches(
        query.text, row.from_address, row.from_name, row.subject, row.untrusted_text
    )
    return select(
        literal(False, Boolean).label("dropped"),
        row.id.label("id"),
        row.from_address.label("from_address"),
        row.from_name.label("from_name"),
        row.subject.label("subject"),
        row.received_at.label("received_at"),
        row.category.label("category"),
        row.sender_auth.label("sender_auth"),
        cast(null(), Text).label("reason"),
    ).where(*filters)


def _dropped_rows(
    user_id: UserId, query: MailQuery, since: datetime
) -> Select[*tuple[Any, ...]]:
    row = MailDroppedRow
    filters = [row.user_id == user_id.value, row.received_at > since]
    filters += matches(query.text, row.from_address, row.subject)
    return select(
        literal(True, Boolean).label("dropped"),
        row.id.label("id"),
        row.from_address.label("from_address"),
        literal("", Text).label("from_name"),
        row.subject.label("subject"),
        row.received_at.label("received_at"),
        cast(null(), Text).label("category"),
        cast(null(), Text).label("sender_auth"),
        row.reason.label("reason"),
    ).where(*filters)


def _summary(row: MailMessageRow) -> MailSummary:
    return MailSummary(
        id=row.id,
        from_address=row.from_address,
        from_name=row.from_name,
        subject=row.subject,
        category=MailCategory(row.category),
        received_at=row.received_at,
        sender_auth=SenderAuth(row.sender_auth),
    )


class PostgresMailSends:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_since(self, moment: datetime) -> int:
        found = await self._session.execute(
            select(func.count())
            .select_from(MailSendRow)
            .where(MailSendRow.sent_at > moment)
        )
        return int(found.scalar_one())

    async def record(self, sent_at: datetime) -> None:
        self._session.add(MailSendRow(sent_at=sent_at))
        await self._session.flush()
