"""ORM-таблиці контексту documents. Назовні адаптера не виходять: лише через repository."""

from datetime import datetime
from typing import Any
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import Base


class DocumentRow(Base):
    """Версія CV чи листа вакансії. Внутрішній ключ — UUID, а людям і MCP показується
    `document_number` (з 1 на користувача). Версії рахуються окремо для кожного виду документа
    вакансії; `content` — JSON тієї ж форми, що в v1, `lint` — знімок ATS-звіту на момент
    збереження (NULL — звіту нема)."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "document_number", name="uq_documents_user_id_document_number"
        ),
        UniqueConstraint(
            "job_id", "kind", "version", name="uq_documents_job_id_kind_version"
        ),
        CheckConstraint("document_number >= 1", name="document_number_positive"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("kind IN ('cv', 'cl')", name="kind_known"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    document_number: Mapped[int] = mapped_column(Integer)
    job_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # none_as_null: «звіту нема» — SQL NULL, а не JSON null.
    lint: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Фото в шапці CV; видалене фото обнуляє зв'язок, документ лишається.
    photo_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("photos.id", ondelete="SET NULL"), index=True
    )


class DocumentCounterRow(Base):
    """Останній виданий номер документа користувача. Номер не повторюється."""

    __tablename__ = "document_counters"
    __table_args__ = (CheckConstraint("last_number >= 0", name="last_number_valid"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(Integer)


class DocumentDownloadLinkRow(Base):
    """Одноразове посилання на PDF документа. Токен у базі не лежить: лише його sha256-дайджест
    (він і є ключем); `used_at` — коли посилання вже відкрили (NULL — ще ні)."""

    __tablename__ = "document_download_links"

    token_digest: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
