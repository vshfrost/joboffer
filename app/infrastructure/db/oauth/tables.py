"""ORM-таблиці контексту oauth. Секретів тут нема: код і токени — лише sha256-дайджести."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import Base


class OAuthClientRow(Base):
    __tablename__ = "oauth_clients"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    redirect_uris: Mapped[list[str]] = mapped_column(JSONB)
    # Документ реєстрації (RFC 7591) без секретів: усі DCR-клієнти публічні.
    registration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OAuthGrantRow(Base):
    __tablename__ = "oauth_grants"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("oauth_clients.id", ondelete="CASCADE"), index=True
    )
    resource: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OAuthTokenRow(Base):
    __tablename__ = "oauth_tokens"

    # sha256-дайджест коду чи токена; сам секрет є лише в клієнта.
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    grant_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("oauth_grants.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(8))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Лише для коду: що клієнт заявив на /authorize.
    code_challenge: Mapped[str | None] = mapped_column(Text)
    redirect_uri: Mapped[str | None] = mapped_column(Text)
    redirect_uri_provided_explicitly: Mapped[bool | None] = mapped_column(Boolean)

    __table_args__ = (
        CheckConstraint("kind IN ('code', 'access', 'refresh')", name="kind"),
    )
