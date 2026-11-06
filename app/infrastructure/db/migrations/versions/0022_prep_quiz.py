"""Квіз підготовки: питання `prep_questions` (UUID + номер на користувача, наскрізний по темах;
коробка Leitner, день повторення), історія відповідей `prep_answers`, лічильник номерів
`prep_question_counters`.

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prep_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("question_number", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("question_hash", sa.Text(), nullable=False),
        sa.Column("answer_points", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("box", sa.Integer(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "question_number >= 1",
            name=op.f("ck_prep_questions_question_number_positive"),
        ),
        sa.CheckConstraint(
            "box BETWEEN 1 AND 5", name=op.f("ck_prep_questions_box_range")
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["prep_topics.id"],
            name=op.f("fk_prep_questions_topic_id_prep_topics"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_prep_questions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prep_questions")),
        sa.UniqueConstraint(
            "topic_id",
            "question_hash",
            name=op.f("uq_prep_questions_topic_id_question_hash"),
        ),
        sa.UniqueConstraint(
            "user_id",
            "question_number",
            name=op.f("uq_prep_questions_user_id_question_number"),
        ),
    )
    op.create_table(
        "prep_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("answer", sa.Text(), server_default="", nullable=False),
        sa.Column("feedback", sa.Text(), server_default="", nullable=False),
        sa.Column("box", sa.Integer(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "grade BETWEEN 0 AND 5", name=op.f("ck_prep_answers_grade_range")
        ),
        sa.CheckConstraint(
            "box BETWEEN 1 AND 5", name=op.f("ck_prep_answers_box_range")
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["prep_questions.id"],
            name=op.f("fk_prep_answers_question_id_prep_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prep_answers")),
    )
    op.create_index("ix_prep_answers_question_id", "prep_answers", ["question_id"])
    op.create_table(
        "prep_question_counters",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "last_number >= 0",
            name=op.f("ck_prep_question_counters_last_number_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_prep_question_counters_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_prep_question_counters")),
    )


def downgrade() -> None:
    op.drop_table("prep_question_counters")
    op.drop_index("ix_prep_answers_question_id", table_name="prep_answers")
    op.drop_table("prep_answers")
    op.drop_table("prep_questions")
