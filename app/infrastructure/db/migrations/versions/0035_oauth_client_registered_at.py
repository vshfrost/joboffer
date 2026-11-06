"""Коли зареєстровано OAuth-клієнта (`oauth_clients.registered_at`).

Публічний DCR `/register` додає клієнтів без автентифікації; за датою можна прибирати тих, що так і не
отримали гранту. Наявні клієнти отримують час міграції, тож не зникнуть раніше за строк прибирання.

Revision ID: 0035
Revises: 0034
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "oauth_clients",
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("oauth_clients", "registered_at")
