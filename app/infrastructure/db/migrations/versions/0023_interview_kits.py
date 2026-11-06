"""Пакет до інтерв'ю: версії `interview_kits` (UUID + номер на користувача; версії рахуються
окремо для кожної вакансії, вміст — JSONB) і лічильник номерів `interview_kit_counters`.

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_kits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kit_number", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kit_number >= 1", name=op.f("ck_interview_kits_kit_number_positive")
        ),
        sa.CheckConstraint(
            "version >= 1", name=op.f("ck_interview_kits_version_positive")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_interview_kits_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_interview_kits_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_kits")),
        sa.UniqueConstraint(
            "job_id", "version", name=op.f("uq_interview_kits_job_id_version")
        ),
        sa.UniqueConstraint(
            "user_id", "kit_number", name=op.f("uq_interview_kits_user_id_kit_number")
        ),
    )
    op.create_table(
        "interview_kit_counters",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "last_number >= 0",
            name=op.f("ck_interview_kit_counters_last_number_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_interview_kit_counters_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_interview_kit_counters")),
    )


def downgrade() -> None:
    op.drop_table("interview_kit_counters")
    op.drop_table("interview_kits")
