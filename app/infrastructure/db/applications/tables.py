"""ORM-таблиця контексту applications. Назовні адаптера не виходить: лише через repository."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import Base


class ApplicationRow(Base):
    """Подача на вакансію: одна на вакансію (ключ — UUID вакансії), деталі й статус окремо.

    Номер вакансії для людей і MCP живе в `jobs`. Домени й адреси компанії — масиви (як у v1).
    """

    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('applied', 'replied', 'interview', 'offer', 'rejected', "
            "'withdrawn')",
            name="status_known",
        ),
        CheckConstraint(
            "channel IN ('email', 'ats', 'linkedin', 'referral')",
            name="channel_known",
        ),
        CheckConstraint(
            "ats IN ('greenhouse', 'lever', 'ashby', 'workable', 'smartrecruiters', "
            "'other')",
            name="ats_known",
        ),
    )

    job_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(Text)
    applied_on: Mapped[date] = mapped_column(Date)
    channel: Mapped[str] = mapped_column(Text)
    ats: Mapped[str | None] = mapped_column(Text)
    company_domains: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'")
    )
    company_emails: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'")
    )
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ApplicationCvVersionRow(Base):
    """Версія CV, з якою подались: номер документа, день збереження й покриття слів вакансії
    (NULL — аналізу тоді не було). Окрема від `applications`, яка лишається колонками v1 для ETL:
    нема рядка — версія «невідома» (подача без CV чи зроблена до цієї таблиці). Файлу тут нема:
    у вакансії лишається лише останнє CV, номер на нього не посилається ключем."""

    __tablename__ = "application_cv_versions"
    __table_args__ = (
        CheckConstraint("cv_number >= 1", name="cv_number_positive"),
        CheckConstraint(
            "coverage_percent BETWEEN 0 AND 100", name="coverage_percent_valid"
        ),
    )

    job_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("applications.job_id", ondelete="CASCADE"), primary_key=True
    )
    cv_number: Mapped[int] = mapped_column(Integer)
    saved_on: Mapped[date] = mapped_column(Date)
    coverage_percent: Mapped[int | None] = mapped_column(Integer)
