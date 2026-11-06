"""ORM-таблиці контексту facts. Назовні адаптера не виходять: лише через repository."""

from datetime import datetime
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
    select,
)
from sqlalchemy.orm import Mapped, column_property, mapped_column

from domain.facts.fact import FactKind, FactSource
from infrastructure.db.base import Base
from infrastructure.db.jobs.tables import JobRow

_KINDS = ", ".join(f"'{kind.value}'" for kind in FactKind)
_SOURCES = ", ".join(f"'{source.value}'" for source in FactSource)


class OriginalCvRow(Base):
    """Оригінал CV: один на користувача, текст з PDF (байти не зберігаються)."""

    __tablename__ = "original_cvs"

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    file_name: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FactRow(Base):
    """Факт. Внутрішній ключ — UUID, а людям і MCP показується `fact_number` (з 1 на користувача).

    Унікальні в межах користувача `fact_number` і `text_hash` (той самий текст без регістру й
    пробілів, хоч і іншого виду).
    """

    __tablename__ = "facts"
    __table_args__ = (
        UniqueConstraint("user_id", "fact_number", name="uq_facts_user_id_fact_number"),
        UniqueConstraint("user_id", "text_hash", name="uq_facts_user_id_text_hash"),
        CheckConstraint("fact_number >= 1", name="fact_number_positive"),
        CheckConstraint(f"kind IN ({_KINDS})", name="kind_known"),
        CheckConstraint(f"source IN ({_SOURCES})", name="source_known"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    fact_number: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(Text)
    confirmed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(Text, server_default=FactSource.CV.value)
    # Вакансія, до якої факт прив'язано; вакансію видалено — факт лишається загальним.
    job_uuid: Mapped[UUID | None] = mapped_column(
        "job_id", Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    # Номер цієї вакансії в користувача — його бачать люди й MCP.
    job_number: Mapped[int | None] = column_property(
        select(JobRow.job_number).where(JobRow.id == job_uuid).scalar_subquery()
    )


class FactCounterRow(Base):
    """Останній виданий номер факту користувача. Номер не повторюється, навіть коли факт видалено."""

    __tablename__ = "fact_counters"
    __table_args__ = (CheckConstraint("last_number >= 0", name="last_number_valid"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(Integer)
