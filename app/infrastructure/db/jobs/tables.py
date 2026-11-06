"""ORM-таблиці контексту jobs. Назовні адаптера не виходять: лише через repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import Base


class JobRow(Base):
    """Вакансія. Внутрішній ключ — UUID, а людям і MCP показується `job_number` (з 1 на користувача).

    `text` NULL — «потрібен текст» (вакансія з листа-алерту). Унікальні в межах користувача
    `job_number`, `text_hash`, `url` і `linkedin_id` (NULL нічого не дублює).
    """

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "job_number", name="uq_jobs_user_id_job_number"),
        UniqueConstraint("user_id", "text_hash", name="uq_jobs_user_id_text_hash"),
        UniqueConstraint("user_id", "url", name="uq_jobs_user_id_url"),
        UniqueConstraint("user_id", "linkedin_id", name="uq_jobs_user_id_linkedin_id"),
        CheckConstraint("job_number >= 1", name="job_number_positive"),
        CheckConstraint(
            "(dismissed_at IS NULL) = (dismiss_reason IS NULL)",
            name="dismissal_complete",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    job_number: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(Text, server_default="manual")
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    text_hash: Mapped[str | None] = mapped_column(Text)
    linkedin_id: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Позначка «нове» (відкрито / ні) — логіка у B10; колонка потрібна для переносу з v1.
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismiss_reason: Mapped[str | None] = mapped_column(Text)


class JobCounterRow(Base):
    """Останній виданий номер вакансії користувача. Номер не повторюється, навіть коли вакансію прибрано."""

    __tablename__ = "job_counters"
    __table_args__ = (CheckConstraint("last_number >= 0", name="last_number_valid"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(Integer)
