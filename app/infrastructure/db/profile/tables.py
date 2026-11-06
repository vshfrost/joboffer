"""ORM-таблиці контексту profile. Назовні адаптера не виходять: лише через repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import Base


class ProfileRow(Base):
    """Профіль: один рядок на користувача, і лише після першого збереження.

    Списки — `text[]`, enum-и — їх значення; порожній рядок / порожній список = «не вказано».
    """

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("min_salary_eur >= 0", name="min_salary_non_negative"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    work_modes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    include_unknown_mode: Mapped[bool] = mapped_column(Boolean, server_default="true")
    relocation: Mapped[bool] = mapped_column(Boolean, server_default="false")
    target_domains: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    seniority: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    min_salary_eur: Mapped[int | None] = mapped_column(Integer)
    stop_words: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    title_keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    title_exclude: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    full_name: Mapped[str] = mapped_column(Text, server_default="")
    email: Mapped[str] = mapped_column(Text, server_default="")
    phone: Mapped[str] = mapped_column(Text, server_default="")
    linkedin_url: Mapped[str] = mapped_column(Text, server_default="")
    city: Mapped[str] = mapped_column(Text, server_default="")
    github_url: Mapped[str] = mapped_column(Text, server_default="")
    work_authorization: Mapped[str] = mapped_column(Text, server_default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Остання зміна цілі, локацій чи правил: від неї аналізи вакансій застарівають.
    analysis_inputs_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class ProfileLocationRow(Base):
    """Де шукаємо: порядок — `position` (як ввів користувач); місце унікальне в користувача без регістру."""

    __tablename__ = "profile_locations"
    __table_args__ = (
        CheckConstraint(
            "cardinality(work_modes) > 0"
            " AND work_modes <@ ARRAY['remote', 'hybrid', 'onsite']",
            name="work_modes_known",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    place: Mapped[str] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    work_modes: Mapped[list[str]] = mapped_column(ARRAY(Text))


Index(
    "uq_profile_locations_user_id_place",
    ProfileLocationRow.user_id,
    func.lower(ProfileLocationRow.place),
    unique=True,
)
