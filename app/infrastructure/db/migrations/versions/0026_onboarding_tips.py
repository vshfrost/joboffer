"""Підказки онбордингу: що користувач бачив і сховав (`onboarding_tips`, рядок лише для баченої).

Revision ID: 0026
Revises: 0023
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
# Паралельні гілки B13-1 мають 0024, 0025, 0027; ланцюг вирівнює автор гілки після мерджу.
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "onboarding_tips",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tip_key", sa.Text(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_onboarding_tips_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "tip_key", name=op.f("pk_onboarding_tips")),
    )


def downgrade() -> None:
    op.drop_table("onboarding_tips")
