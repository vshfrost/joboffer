"""Відповіді користувача на прогалини вакансій: `gap_answers` (за текстом прогалини) і
`gap_answer_facts` (факти, що закривають прогалину).

Revision ID: 0031
Revises: 0030
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gap_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("gap", sa.Text(), nullable=False),
        sa.Column("gap_hash", sa.Text(), nullable=False),
        sa.Column("has_experience", sa.Boolean(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_gap_answers_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_gap_answers_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gap_answers")),
        sa.UniqueConstraint(
            "job_id", "gap_hash", name=op.f("uq_gap_answers_job_id_gap_hash")
        ),
    )
    op.create_table(
        "gap_answer_facts",
        sa.Column("gap_answer_id", sa.Uuid(), nullable=False),
        sa.Column("fact_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fact_id"],
            ["facts.id"],
            name=op.f("fk_gap_answer_facts_fact_id_facts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["gap_answer_id"],
            ["gap_answers.id"],
            name=op.f("fk_gap_answer_facts_gap_answer_id_gap_answers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "gap_answer_id", "fact_id", name=op.f("pk_gap_answer_facts")
        ),
    )


def downgrade() -> None:
    op.drop_table("gap_answer_facts")
    op.drop_table("gap_answers")
