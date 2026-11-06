"""ORM-таблиці контексту analysis. Назовні адаптера не виходять: лише через repository."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import Base


class AnalysisRow(Base):
    """Повний аналіз вакансії: один на вакансію (повторний замінює). Колонки `score`, `work_mode`
    і `filters_passed` — для сортування й фільтра списку, решта розбору — у `details` (JSON),
    `flags` — знімок фільтрів профілю на момент збереження."""

    __tablename__ = "job_analyses"
    __table_args__ = (CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    job_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), unique=True
    )
    score: Mapped[int] = mapped_column(Integer)
    work_mode: Mapped[str | None] = mapped_column(Text)
    filters_passed: Mapped[bool] = mapped_column(Boolean)
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GapAnswerRow(Base):
    """Відповідь користувача на прогалину вакансії. Прив'язана до тексту прогалини (`gap_hash` —
    відбиток без регістру й зайвих пробілів), а не до номера: повторний аналіз із тією самою
    прогалиною знову її бачить. Одна відповідь на текст у межах вакансії."""

    __tablename__ = "gap_answers"
    __table_args__ = (
        UniqueConstraint("job_id", "gap_hash", name="uq_gap_answers_job_id_gap_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    job_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE")
    )
    gap: Mapped[str] = mapped_column(Text)
    gap_hash: Mapped[str] = mapped_column(Text)
    has_experience: Mapped[bool] = mapped_column(Boolean)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GapAnswerFactRow(Base):
    """Факт, що закриває прогалину; `position` — порядок, у якому користувач їх схвалив.
    Факт видалено — зв'язок зникає, відповідь лишається."""

    __tablename__ = "gap_answer_facts"

    gap_answer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("gap_answers.id", ondelete="CASCADE"), primary_key=True
    )
    fact_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("facts.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer)
