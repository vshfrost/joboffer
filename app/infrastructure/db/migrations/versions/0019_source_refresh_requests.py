"""Запити «оновити зараз» для джерел (`source_refresh_requests`): ліміт 2 за 30 хв на користувача,
прогін джерел позначає виконані. Колонки як у v1 — ETL у B12 переносить їх без втрат.

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_refresh_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_source_refresh_requests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_refresh_requests")),
    )
    op.create_index(
        "ix_source_refresh_requests_user_id_requested_at",
        "source_refresh_requests",
        ["user_id", "requested_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_refresh_requests_user_id_requested_at",
        table_name="source_refresh_requests",
    )
    op.drop_table("source_refresh_requests")
