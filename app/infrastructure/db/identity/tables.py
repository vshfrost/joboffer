"""ORM-таблиці контексту identity. Назовні адаптера не виходять: лише через repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain.identity.email import EMAIL_MAX
from domain.identity.user import DISPLAY_NAME_MAX
from infrastructure.db.base import Base


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # Email зберігається вже нормалізованим (нижній регістр), тож звичайний unique ловить дублі.
    email: Mapped[str] = mapped_column(String(EMAIL_MAX), unique=True)
    display_name: Mapped[str] = mapped_column(String(DISPLAY_NAME_MAX))
    # NULL — користувач без пароля (створений входом через Google).
    password_hash: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Згода з умовами при реєстрації: версія тексту й момент; NULL — користувач до появи згоди.
    terms_version: Mapped[str | None] = mapped_column(String(32))
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Лише sha256-дайджест токена: сам токен є тільки в cookie користувача.
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LoginFailureRow(Base):
    __tablename__ = "login_failures"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64))
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_login_failures_key_failed_at", "key", "failed_at"),)


class AltchaSolutionRow(Base):
    __tablename__ = "altcha_solutions"

    # HMAC-підпис задачі (hex sha256): унікальний на задачу, тож повторний розв'язок його не вставить.
    signature: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class UserIdentityRow(Base):
    __tablename__ = "user_identities"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("provider", "subject"),)


class SignupInviteRow(Base):
    __tablename__ = "signup_invites"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # Лише sha256-дайджест токена: сам токен є тільки в посиланні, яке отримав запрошений.
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # NULL — ще не використане.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SignupRequestRow(Base):
    __tablename__ = "signup_requests"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # Один запит на email: повторна реєстрація замінює попередній.
    email: Mapped[str] = mapped_column(String(EMAIL_MAX), unique=True)
    # Лише хеш пароля й sha256-дайджест коду: ні пароля, ні коду в базі нема.
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(DISPLAY_NAME_MAX))
    invite_digest: Mapped[str] = mapped_column(String(64))
    terms_version: Mapped[str] = mapped_column(String(32))
    code_digest: Mapped[str] = mapped_column(String(64))
    failed_attempts: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SignupLimitRow(Base):
    __tablename__ = "signup_limits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # sha256-ключ клієнта чи email (domain/identity/throttle.py): адрес у базі нема.
    key: Mapped[str] = mapped_column(String(64))
    hit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_signup_limits_key_hit_at", "key", "hit_at"),)
