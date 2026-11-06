"""ORM-таблиці контексту sources. Назовні адаптера не виходять: лише через repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import Base

# Коди збою джерела (`domain.sources.failure.FailureReason`) — контракт стану прогону.
ERROR_KNOWN = (
    "error IS NULL OR error IN ('timeout', 'not_found', 'rate_limited', 'unavailable',"
    " 'rejected', 'invalid', 'unsupported')"
)


class SourceCompanyRow(Base):
    """Компанія ATS у списку користувача: платформа + слаг."""

    __tablename__ = "source_companies"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "platform",
            "slug",
            name="uq_source_companies_user_id_platform_slug",
        ),
        CheckConstraint(
            "platform IN ('greenhouse', 'ashby', 'lever')", name="platform_known"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    platform: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, server_default="")
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SourceFeedRow(Base):
    """RSS-стрічка користувача: джерело (DOU, Djinni) + запит."""

    __tablename__ = "source_feeds"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "source", "query", name="uq_source_feeds_user_id_source_query"
        ),
        CheckConstraint("source IN ('dou', 'djinni')", name="source_known"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(Text)
    query: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SourceCompanyRunRow(Base):
    """Останній прогін компанії: один рядок на джерело користувача; зникає разом з компанією."""

    __tablename__ = "source_company_runs"
    __table_args__ = (CheckConstraint(ERROR_KNOWN, name="error_known"),)

    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("source_companies.id", ondelete="CASCADE"), primary_key=True
    )
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    found: Mapped[int] = mapped_column(Integer)
    imported: Mapped[int] = mapped_column(Integer)
    filtered: Mapped[int] = mapped_column(Integer)
    duplicate: Mapped[int] = mapped_column(Integer)
    completed: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


class SourceFeedRunRow(Base):
    """Останній прогін стрічки: один рядок на джерело користувача; зникає разом зі стрічкою."""

    __tablename__ = "source_feed_runs"
    __table_args__ = (CheckConstraint(ERROR_KNOWN, name="error_known"),)

    feed_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("source_feeds.id", ondelete="CASCADE"), primary_key=True
    )
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    found: Mapped[int] = mapped_column(Integer)
    imported: Mapped[int] = mapped_column(Integer)
    filtered: Mapped[int] = mapped_column(Integer)
    duplicate: Mapped[int] = mapped_column(Integer)
    completed: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


class SourceRefreshRequestRow(Base):
    """Запит користувача «оновити зараз» (ліміт 2 за 30 хв). Прогін джерел позначає запити виконаними
    (`handled_at`) і при цьому не зменшує ліміт: вікно рахує запити."""

    __tablename__ = "source_refresh_requests"
    __table_args__ = (
        Index(
            "ix_source_refresh_requests_user_id_requested_at",
            "user_id",
            "requested_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
