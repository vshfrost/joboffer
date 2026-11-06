"""Повний аналіз вакансій: `job_analyses` (UUID, один аналіз на вакансію) і час останньої зміни
цілі, локацій чи правил у профілі (`profiles.analysis_inputs_changed_at`) — від нього аналізи
застарівають.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("work_mode", sa.Text(), nullable=True),
        sa.Column("filters_passed", sa.Boolean(), nullable=False),
        sa.Column(
            "flags",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "score BETWEEN 0 AND 100", name=op.f("ck_job_analyses_score_range")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_analyses_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_job_analyses_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_analyses")),
        sa.UniqueConstraint("job_id", name=op.f("uq_job_analyses_job_id")),
    )
    op.add_column(
        "profiles",
        sa.Column(
            "analysis_inputs_changed_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("profiles", "analysis_inputs_changed_at")
    op.drop_table("job_analyses")
