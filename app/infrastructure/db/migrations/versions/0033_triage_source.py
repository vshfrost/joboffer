"""Хто оцінив тріаж (`source`: agent | rules) і відбиток вхідних даних (`inputs_hash`).

Наявні рядки — від Claude (`agent`), відбитка в них нема. Тріаж за правилами (cron без LLM)
перераховується, коли відбиток змінюється; `agent` його не торкається.

Revision ID: 0033
Revises: 0032
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_triage",
        sa.Column("source", sa.Text(), server_default="agent", nullable=False),
    )
    op.add_column("job_triage", sa.Column("inputs_hash", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_job_triage_source_known"),
        "job_triage",
        "source IN ('agent', 'rules')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_job_triage_source_known"), "job_triage", type_="check")
    op.drop_column("job_triage", "inputs_hash")
    op.drop_column("job_triage", "source")
