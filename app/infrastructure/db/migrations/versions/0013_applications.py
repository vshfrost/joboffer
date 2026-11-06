"""Подачі на вакансії: `applications` (ключ — UUID вакансії; дата, канал, ATS, домени й адреси
компанії, статус і час його зміни). Усі колонки v1 збережено — ETL у B12 переносить їх без втрат.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("applied_on", sa.Date(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("ats", sa.Text(), nullable=True),
        sa.Column(
            "company_domains",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "company_emails",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('applied', 'replied', 'interview', 'offer', 'rejected', "
            "'withdrawn')",
            name=op.f("ck_applications_status_known"),
        ),
        sa.CheckConstraint(
            "channel IN ('email', 'ats', 'linkedin', 'referral')",
            name=op.f("ck_applications_channel_known"),
        ),
        sa.CheckConstraint(
            "ats IN ('greenhouse', 'lever', 'ashby', 'workable', 'smartrecruiters', "
            "'other')",
            name=op.f("ck_applications_ats_known"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_applications_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_applications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_applications")),
    )
    op.create_index(op.f("ix_applications_user_id"), "applications", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_applications_user_id"), table_name="applications")
    op.drop_table("applications")
