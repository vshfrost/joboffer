"""Реєстрація: `signup_requests` (дані чекають код з листа, лише хеш пароля й digest коду) і
`signup_limits` (ліміти реєстрації з вікном до години, лише дайджести ключів).

Revision ID: 0028
Revises: 0025
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signup_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("invite_digest", sa.String(length=64), nullable=False),
        sa.Column("terms_version", sa.String(length=32), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signup_requests")),
        sa.UniqueConstraint("email", name=op.f("uq_signup_requests_email")),
    )
    op.create_index("ix_signup_requests_expires_at", "signup_requests", ["expires_at"])
    op.create_table(
        "signup_limits",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("hit_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signup_limits")),
    )
    op.create_index("ix_signup_limits_key_hit_at", "signup_limits", ["key", "hit_at"])


def downgrade() -> None:
    op.drop_index("ix_signup_limits_key_hit_at", table_name="signup_limits")
    op.drop_table("signup_limits")
    op.drop_index("ix_signup_requests_expires_at", table_name="signup_requests")
    op.drop_table("signup_requests")
