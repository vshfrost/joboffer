"""Факти: `original_cvs`, `facts` (UUID + номер на користувача) і лічильник номерів `fact_counters`.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "original_cvs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_original_cvs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_original_cvs")),
    )
    op.create_table(
        "facts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("fact_number", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.Text(), nullable=False),
        sa.Column(
            "confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "fact_number >= 1", name=op.f("ck_facts_fact_number_positive")
        ),
        sa.CheckConstraint(
            "kind IN ('experience', 'achievement', 'project', 'skill', "
            "'education', 'language')",
            name=op.f("ck_facts_kind_known"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_facts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_facts")),
        sa.UniqueConstraint(
            "user_id", "fact_number", name=op.f("uq_facts_user_id_fact_number")
        ),
        sa.UniqueConstraint(
            "user_id", "text_hash", name=op.f("uq_facts_user_id_text_hash")
        ),
    )
    op.create_table(
        "fact_counters",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "last_number >= 0", name=op.f("ck_fact_counters_last_number_valid")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_fact_counters_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_fact_counters")),
    )


def downgrade() -> None:
    op.drop_table("fact_counters")
    op.drop_table("facts")
    op.drop_table("original_cvs")
