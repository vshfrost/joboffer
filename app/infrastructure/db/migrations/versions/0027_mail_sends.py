"""Журнал відправлень листів застосунку `mail_sends` (лише момент): основа добового ліміту.

Revision ID: 0027
Revises: 0026
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mail_sends",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mail_sends")),
    )
    op.create_index("ix_mail_sends_sent_at", "mail_sends", ["sent_at"])


def downgrade() -> None:
    op.drop_index("ix_mail_sends_sent_at", table_name="mail_sends")
    op.drop_table("mail_sends")
