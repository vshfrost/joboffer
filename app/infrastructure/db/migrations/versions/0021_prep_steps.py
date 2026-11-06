"""План теми підготовки: кроки `prep_steps` (UUID + номер на користувача, наскрізний по темах),
лічильник номерів `prep_step_counters` і позначка «готово» `prep_topics.ready_at`.

Revision ID: 0021
Revises: 0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prep_topics",
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "prep_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), server_default="", nullable=False),
        sa.Column("resources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.CheckConstraint(
            "step_number >= 1", name=op.f("ck_prep_steps_step_number_positive")
        ),
        sa.CheckConstraint(
            "position >= 1", name=op.f("ck_prep_steps_position_positive")
        ),
        sa.CheckConstraint(
            "kind IN ('learn', 'practice', 'check')",
            name=op.f("ck_prep_steps_kind_known"),
        ),
        sa.CheckConstraint("minutes > 0", name=op.f("ck_prep_steps_minutes_positive")),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["prep_topics.id"],
            name=op.f("fk_prep_steps_topic_id_prep_topics"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_prep_steps_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prep_steps")),
        sa.UniqueConstraint(
            "topic_id", "position", name=op.f("uq_prep_steps_topic_id_position")
        ),
        sa.UniqueConstraint(
            "user_id", "step_number", name=op.f("uq_prep_steps_user_id_step_number")
        ),
    )
    op.create_table(
        "prep_step_counters",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "last_number >= 0", name=op.f("ck_prep_step_counters_last_number_valid")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_prep_step_counters_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_prep_step_counters")),
    )


def downgrade() -> None:
    op.drop_table("prep_step_counters")
    op.drop_table("prep_steps")
    op.drop_column("prep_topics", "ready_at")
