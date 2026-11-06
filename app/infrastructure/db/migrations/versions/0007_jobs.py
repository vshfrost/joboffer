"""Вакансії: `jobs` (UUID + номер на користувача) і лічильник номерів `job_counters`.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_number", sa.Integer(), nullable=False),
        sa.Column(
            "source", sa.Text(), nullable=False, server_default=sa.text("'manual'")
        ),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("text_hash", sa.Text(), nullable=True),
        sa.Column("linkedin_id", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismiss_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("job_number >= 1", name=op.f("ck_jobs_job_number_positive")),
        sa.CheckConstraint(
            "(dismissed_at IS NULL) = (dismiss_reason IS NULL)",
            name=op.f("ck_jobs_dismissal_complete"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_jobs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint(
            "user_id", "job_number", name=op.f("uq_jobs_user_id_job_number")
        ),
        sa.UniqueConstraint(
            "user_id", "text_hash", name=op.f("uq_jobs_user_id_text_hash")
        ),
        sa.UniqueConstraint("user_id", "url", name=op.f("uq_jobs_user_id_url")),
        sa.UniqueConstraint(
            "user_id", "linkedin_id", name=op.f("uq_jobs_user_id_linkedin_id")
        ),
    )
    op.create_table(
        "job_counters",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "last_number >= 0", name=op.f("ck_job_counters_last_number_valid")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_job_counters_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_job_counters")),
    )


def downgrade() -> None:
    op.drop_table("job_counters")
    op.drop_table("jobs")
