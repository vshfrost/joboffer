"""ORM-таблиці контексту prep. Назовні адаптера не виходять: лише через repository."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from domain.prep.plan import StepKind
from domain.prep.topic import TopicKind
from infrastructure.db.base import Base

_KINDS = ", ".join(f"'{kind.value}'" for kind in TopicKind)
_STEP_KINDS = ", ".join(f"'{kind.value}'" for kind in StepKind)


class PrepTopicRow(Base):
    """Тема підготовки. Внутрішній ключ — UUID, а людям і MCP показується `topic_number`
    (з 1 на користувача). Унікальні в межах користувача `topic_number` і `slug`."""

    __tablename__ = "prep_topics"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "topic_number", name="uq_prep_topics_user_id_topic_number"
        ),
        UniqueConstraint("user_id", "slug", name="uq_prep_topics_user_id_slug"),
        CheckConstraint("topic_number >= 1", name="topic_number_positive"),
        CheckConstraint(f"kind IN ({_KINDS})", name="kind_known"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    topic_number: Mapped[int] = mapped_column(Integer)
    slug: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, server_default="")
    deadline: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Коли користувач позначив тему готовою; лише він це робить, статус інакше рахується з кроків.
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PrepTopicCounterRow(Base):
    """Останній виданий номер теми користувача. Номер не повторюється, навіть коли тему видалено."""

    __tablename__ = "prep_topic_counters"
    __table_args__ = (CheckConstraint("last_number >= 0", name="last_number_valid"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(Integer)


class PrepTopicJobRow(Base):
    """Прив'язка «тема + вакансія» з прогалиною, яку тема закриває: одна на пару."""

    __tablename__ = "prep_topic_jobs"
    __table_args__ = (Index("ix_prep_topic_jobs_job_id", "job_id"),)

    topic_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("prep_topics.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    gap: Mapped[str] = mapped_column(Text)


class PrepStepRow(Base):
    """Крок плану теми. Внутрішній ключ — UUID, а людям і MCP показується `step_number` (з 1 на
    користувача, наскрізно по його темах, тому `user_id` тут же). `position` — порядок у темі."""

    __tablename__ = "prep_steps"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "step_number", name="uq_prep_steps_user_id_step_number"
        ),
        UniqueConstraint(
            "topic_id", "position", name="uq_prep_steps_topic_id_position"
        ),
        CheckConstraint("step_number >= 1", name="step_number_positive"),
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint(f"kind IN ({_STEP_KINDS})", name="kind_known"),
        CheckConstraint("minutes > 0", name="minutes_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    topic_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("prep_topics.id", ondelete="CASCADE")
    )
    step_number: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text, server_default="")
    resources: Mapped[list[dict[str, str]]] = mapped_column(JSONB)
    minutes: Mapped[int] = mapped_column(Integer)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(Text, server_default="")


class PrepStepCounterRow(Base):
    """Останній виданий номер кроку користувача. Номер не повторюється, навіть коли крок видалено."""

    __tablename__ = "prep_step_counters"
    __table_args__ = (CheckConstraint("last_number >= 0", name="last_number_valid"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(Integer)


class PrepQuestionRow(Base):
    """Питання квізу. Внутрішній ключ — UUID, а людям і MCP показується `question_number` (з 1 на
    користувача, наскрізно по його темах, тому `user_id` тут же). `question_hash` — відбиток
    тексту без пробілів і регістру: дубль у темі неможливий. Коробка Leitner — 1–5, `due_on` —
    день повторення за Мадридом."""

    __tablename__ = "prep_questions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "question_number",
            name="uq_prep_questions_user_id_question_number",
        ),
        UniqueConstraint(
            "topic_id", "question_hash", name="uq_prep_questions_topic_id_question_hash"
        ),
        CheckConstraint("question_number >= 1", name="question_number_positive"),
        CheckConstraint("box BETWEEN 1 AND 5", name="box_range"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    topic_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("prep_topics.id", ondelete="CASCADE")
    )
    question_number: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    question_hash: Mapped[str] = mapped_column(Text)
    answer_points: Mapped[list[str]] = mapped_column(ARRAY(Text))
    box: Mapped[int] = mapped_column(Integer)
    due_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PrepAnswerRow(Base):
    """Спроба відповіді на питання: оцінка 0–5, відповідь, фідбек і коробка питання після неї."""

    __tablename__ = "prep_answers"
    __table_args__ = (
        Index("ix_prep_answers_question_id", "question_id"),
        CheckConstraint("grade BETWEEN 0 AND 5", name="grade_range"),
        CheckConstraint("box BETWEEN 1 AND 5", name="box_range"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    question_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("prep_questions.id", ondelete="CASCADE")
    )
    grade: Mapped[int] = mapped_column(Integer)
    answer: Mapped[str] = mapped_column(Text, server_default="")
    feedback: Mapped[str] = mapped_column(Text, server_default="")
    box: Mapped[int] = mapped_column(Integer)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PrepQuestionCounterRow(Base):
    """Останній виданий номер питання користувача. Номер не повторюється, навіть коли питання видалено."""

    __tablename__ = "prep_question_counters"
    __table_args__ = (CheckConstraint("last_number >= 0", name="last_number_valid"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(Integer)


class InterviewKitRow(Base):
    """Версія пакета до інтерв'ю під вакансію. Внутрішній ключ — UUID, а людям і MCP показується
    `kit_number` (з 1 на користувача). Версії рахуються окремо для кожної вакансії; `content` —
    JSON тієї ж форми, що в v1 (питання, історії, питання до компанії)."""

    __tablename__ = "interview_kits"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "kit_number", name="uq_interview_kits_user_id_kit_number"
        ),
        UniqueConstraint("job_id", "version", name="uq_interview_kits_job_id_version"),
        CheckConstraint("kit_number >= 1", name="kit_number_positive"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    kit_number: Mapped[int] = mapped_column(Integer)
    job_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InterviewKitCounterRow(Base):
    """Останній виданий номер версії пакета користувача. Номер не повторюється."""

    __tablename__ = "interview_kit_counters"
    __table_args__ = (CheckConstraint("last_number >= 0", name="last_number_valid"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(Integer)
