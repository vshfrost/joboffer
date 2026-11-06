"""ORM-таблиці контексту photos. Назовні адаптера не виходять: лише через repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import Base


class PhotoRow(Base):
    """Фото для шапки CV. Внутрішній ключ — UUID, а людям і MCP показується `photo_number`
    (з 1 на користувача). `data` — нормалізований JPEG (`bytea`), `width` і `height` — його розміри."""

    __tablename__ = "photos"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "photo_number", name="uq_photos_user_id_photo_number"
        ),
        CheckConstraint("photo_number >= 1", name="photo_number_positive"),
        CheckConstraint("width >= 1 AND height >= 1", name="size_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    photo_number: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(Text)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PhotoCounterRow(Base):
    """Останній виданий номер фото користувача. Номер не повторюється, навіть коли фото видалено."""

    __tablename__ = "photo_counters"
    __table_args__ = (CheckConstraint("last_number >= 0", name="last_number_valid"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(Integer)
