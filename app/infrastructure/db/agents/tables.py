"""ORM-таблиці контексту agents. Назовні адаптера не виходять: лише через repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import Base


class UserAgentRow(Base):
    """Агент користувача: один рядок на (користувач, OAuth-клієнт). `grant_id` — найновіший грант."""

    __tablename__ = "user_agents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    client_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("oauth_clients.id", ondelete="CASCADE")
    )
    grant_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("oauth_grants.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("user_id", "client_id"),)
