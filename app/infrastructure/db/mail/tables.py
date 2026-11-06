"""ORM-таблиці контексту mail. Назовні адаптера не виходять: лише через repository."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import Base


class MailInboxRow(Base):
    """Особиста адреса користувача в скриньці застосунку: випадковий tag, один на користувача."""

    __tablename__ = "mail_inboxes"

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MailRetiredTagRow(Base):
    """Колишній tag користувача (до ротації): листи на нього синк не зберігає, а лише записує."""

    __tablename__ = "mail_retired_tags"

    tag: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    retired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MailSyncStateRow(Base):
    """Синк скриньки застосунку: курсор змін Gmail (`history_id`) і остання помилка."""

    __tablename__ = "mail_sync_state"

    mailbox: Mapped[str] = mapped_column(Text, primary_key=True)
    history_id: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str] = mapped_column(Text, server_default="")
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MailSyncRequestRow(Base):
    """Запит користувача синкнути пошту вручну (ліміт 2 за 30 хв). Процес синку позначає
    запити виконаними (`handled_at`) і при цьому не зменшує ліміт: вікно рахує запити."""

    __tablename__ = "mail_sync_requests"
    __table_args__ = (
        Index("ix_mail_sync_requests_user_id_requested_at", "user_id", "requested_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MailMessageRow(Base):
    """Збережений лист користувача. Текст, тема, відправник — недовірені дані третіх сторін;
    текст зберігається обрізаним (64 КБ), вкладення — лише описом."""

    __tablename__ = "mail_messages"
    __table_args__ = (
        CheckConstraint(
            "category IN ('company', 'linkedin_alert', 'linkedin_application', "
            "'linkedin_message', 'forwarding_confirmation', 'suspicious', 'other')",
            name="category_known",
        ),
        CheckConstraint(
            "sender_auth IN ('verified', 'failed', 'unknown')",
            name="sender_auth_known",
        ),
        Index("ix_mail_messages_user_id_received_at", "user_id", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    gmail_id: Mapped[str] = mapped_column(Text, unique=True)
    message_id: Mapped[str] = mapped_column(Text, server_default="")
    in_reply_to: Mapped[str] = mapped_column(Text, server_default="")
    reference_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'")
    )
    from_address: Mapped[str] = mapped_column(Text, server_default="")
    from_name: Mapped[str] = mapped_column(Text, server_default="")
    to_addresses: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'")
    )
    subject: Mapped[str] = mapped_column(Text, server_default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    category: Mapped[str] = mapped_column(Text)
    sender_auth: Mapped[str] = mapped_column(Text, server_default="unknown")
    untrusted_text: Mapped[str] = mapped_column(Text, server_default="")
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    parse_error: Mapped[str] = mapped_column(Text, server_default="")
    # Коли синк розібрав лист linkedin_alert у вакансії; NULL — ще ні.
    alerts_processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MailDroppedRow(Base):
    """Відкинутий лист з відомим власником: причина, коли надійшов, адреса відправника й тема
    (до 200 символів). Тексту листа тут нема."""

    __tablename__ = "mail_dropped"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('daily_limit', 'retired_tag')", name="reason_known"
        ),
        Index(
            "ix_mail_dropped_user_id_reason_received_at",
            "user_id",
            "reason",
            "received_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    gmail_id: Mapped[str] = mapped_column(Text, unique=True)
    reason: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    from_address: Mapped[str] = mapped_column(Text, server_default="")
    subject: Mapped[str] = mapped_column(Text, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JobReplyRow(Base):
    """Зіставлення листа компанії (`mail_messages`) з вакансією користувача і розбір: впевненість,
    ознака збігу, підказаний і підтверджений тип. Вакансія NULL — лист не про подачу (або її
    видалено). Один лист — одна відповідь. Колонки збігаються з v1 — ETL у B12 переносить їх без втрат."""

    __tablename__ = "job_replies"
    __table_args__ = (
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')", name="confidence_known"
        ),
        CheckConstraint(
            "matched_by IN ('thread', 'email', 'domain', 'ats', 'name')",
            name="matched_by_known",
        ),
        CheckConstraint(
            "suggested_type IN ('auto_confirmation', 'rejection', 'invitation', "
            "'assignment', 'other')",
            name="suggested_type_known",
        ),
        CheckConstraint(
            "type IN ('auto_confirmation', 'rejection', 'invitation', 'assignment', "
            "'other')",
            name="type_known",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mail_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("mail_messages.id", ondelete="CASCADE"), unique=True
    )
    job_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL")
    )
    confidence: Mapped[str | None] = mapped_column(Text)
    matched_by: Mapped[str | None] = mapped_column(Text)
    suggested_type: Mapped[str] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MailSendRow(Base):
    """Успішне відправлення листа застосунку: лише момент (для добового ліміту), без адреси й тексту."""

    __tablename__ = "mail_sends"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_mail_sends_sent_at", "sent_at"),)
