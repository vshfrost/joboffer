"""ORM-таблиці контексту triage. Назовні адаптера не виходять: лише через repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from domain.triage.triage import TriageSource
from infrastructure.db.base import Base


class TriageRow(Base):
    """Швидкий тріаж вакансії: один на вакансію (повторний перезаписує). Повний аналіз — окремо.

    Внутрішній ключ — UUID, а вакансія — своїм UUID: номер для людей і MCP живе в `jobs`.
    """

    __tablename__ = "job_triage"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),
        CheckConstraint(
            "verdict IN ('skip', 'maybe', 'analyse')", name="verdict_known"
        ),
        CheckConstraint("source IN ('agent', 'rules')", name="source_known"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    job_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), unique=True
    )
    score: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    triaged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Хто оцінив (`TriageSource`): рядок `agent` cron не перезаписує.
    source: Mapped[str] = mapped_column(Text, server_default=TriageSource.AGENT.value)
    # Відбиток вхідних даних тріажу `rules` (вакансія, профіль, підтверджені факти); у `agent` — NULL.
    inputs_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
