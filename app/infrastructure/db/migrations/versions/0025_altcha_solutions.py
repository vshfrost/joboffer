"""Використані розв'язки altcha: `altcha_solutions` (підпис задачі + строк, після якого запис можна прибрати).

Revision ID: 0025
Revises: 0024
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "altcha_solutions",
        sa.Column("signature", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("signature", name=op.f("pk_altcha_solutions")),
    )
    op.create_index(
        op.f("ix_altcha_solutions_expires_at"), "altcha_solutions", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_altcha_solutions_expires_at"), table_name="altcha_solutions")
    op.drop_table("altcha_solutions")
