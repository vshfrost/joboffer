"""Запрошення на реєстрацію: `signup_invites` (лише sha256 токена) і згода з умовами в `users`
(`terms_version`, `terms_accepted_at`; NULL у наявних користувачів).

Revision ID: 0024
Revises: 0027
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signup_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signup_invites")),
        sa.UniqueConstraint(
            "token_digest", name=op.f("uq_signup_invites_token_digest")
        ),
    )
    op.add_column(
        "users", sa.Column("terms_version", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "terms_version")
    op.drop_table("signup_invites")
