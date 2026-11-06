"""Листи-алерти LinkedIn → вакансії: `mail_messages.alerts_processed_at` (коли синк розібрав лист
у вакансії). Алерти, що вже лежать у базі, позначаються обробленими (як у v1 0024): у вакансії
вони не імпортуються.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mail_messages",
        sa.Column("alerts_processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE mail_messages SET alerts_processed_at = now() "
        "WHERE category = 'linkedin_alert'"
    )


def downgrade() -> None:
    op.drop_column("mail_messages", "alerts_processed_at")
