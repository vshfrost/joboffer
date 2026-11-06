"""Швидкий тріаж вакансій: `job_triage` (UUID, одна вакансія — один тріаж).

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_triage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("triaged_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "score BETWEEN 0 AND 100", name=op.f("ck_job_triage_score_range")
        ),
        sa.CheckConstraint(
            "verdict IN ('skip', 'maybe', 'analyse')",
            name=op.f("ck_job_triage_verdict_known"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_triage_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_job_triage_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_triage")),
        sa.UniqueConstraint("job_id", name=op.f("uq_job_triage_job_id")),
    )


def downgrade() -> None:
    op.drop_table("job_triage")
