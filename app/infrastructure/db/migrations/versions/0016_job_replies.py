"""Відповіді на подачі (`job_replies`): зіставлення листа компанії з вакансією користувача,
впевненість, ознака збігу, підказаний і підтверджений тип. Колонки v1 збережено — ETL у B12
переносить їх без втрат.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TYPES = "'auto_confirmation', 'rejection', 'invitation', 'assignment', 'other'"


def upgrade() -> None:
    op.create_table(
        "job_replies",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("mail_id", sa.BigInteger(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("confidence", sa.Text(), nullable=True),
        sa.Column("matched_by", sa.Text(), nullable=True),
        sa.Column("suggested_type", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name=op.f("ck_job_replies_confidence_known"),
        ),
        sa.CheckConstraint(
            "matched_by IN ('thread', 'email', 'domain', 'ats', 'name')",
            name=op.f("ck_job_replies_matched_by_known"),
        ),
        sa.CheckConstraint(
            f"suggested_type IN ({TYPES})",
            name=op.f("ck_job_replies_suggested_type_known"),
        ),
        sa.CheckConstraint(
            f"type IN ({TYPES})", name=op.f("ck_job_replies_type_known")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_replies_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["mail_id"],
            ["mail_messages.id"],
            name=op.f("fk_job_replies_mail_id_mail_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_job_replies_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_replies")),
        sa.UniqueConstraint("mail_id", name=op.f("uq_job_replies_mail_id")),
    )
    op.create_index(op.f("ix_job_replies_user_id"), "job_replies", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_job_replies_user_id"), table_name="job_replies")
    op.drop_table("job_replies")
