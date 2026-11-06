"""Джерело факту (`source`: cv | chat | manual) і необов'язкова вакансія (`job_id`).

Наявні факти — з CV: `source = 'cv'`, `job_id` порожній. Вакансію видалено — `job_id` стає NULL,
факт лишається.

Revision ID: 0030
Revises: 0029
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "facts",
        sa.Column("source", sa.Text(), server_default="cv", nullable=False),
    )
    op.add_column("facts", sa.Column("job_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        op.f("ck_facts_source_known"), "facts", "source IN ('cv', 'chat', 'manual')"
    )
    op.create_foreign_key(
        op.f("fk_facts_job_id_jobs"),
        "facts",
        "jobs",
        ["job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_facts_job_id", "facts", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_facts_job_id", table_name="facts")
    op.drop_constraint(op.f("fk_facts_job_id_jobs"), "facts", type_="foreignkey")
    op.drop_constraint(op.f("ck_facts_source_known"), "facts", type_="check")
    op.drop_column("facts", "job_id")
    op.drop_column("facts", "source")
