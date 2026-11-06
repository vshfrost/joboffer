"""Запити синку пошти вручну (`mail_sync_requests`): ліміт 2 за 30 хв, процес синку позначає
виконані. Колонки як у v1 — ETL у B12 переносить їх без втрат.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mail_sync_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_mail_sync_requests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mail_sync_requests")),
    )
    op.create_index(
        "ix_mail_sync_requests_user_id_requested_at",
        "mail_sync_requests",
        ["user_id", "requested_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mail_sync_requests_user_id_requested_at", table_name="mail_sync_requests"
    )
    op.drop_table("mail_sync_requests")
