"""Документи під вакансію: `documents` (UUID + номер на користувача, версії CV і листа окремо
для кожної вакансії) і лічильник номерів `document_counters`. `lint` — знімок ATS-звіту на момент
збереження, заповнюється з K26.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_number", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lint", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "document_number >= 1", name=op.f("ck_documents_document_number_positive")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_documents_version_positive")),
        sa.CheckConstraint(
            "kind IN ('cv', 'cl')", name=op.f("ck_documents_kind_known")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_documents_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_documents_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint(
            "job_id", "kind", "version", name=op.f("uq_documents_job_id_kind_version")
        ),
        sa.UniqueConstraint(
            "user_id",
            "document_number",
            name=op.f("uq_documents_user_id_document_number"),
        ),
    )
    op.create_table(
        "document_counters",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "last_number >= 0", name=op.f("ck_document_counters_last_number_valid")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_document_counters_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_document_counters")),
    )


def downgrade() -> None:
    op.drop_table("document_counters")
    op.drop_table("documents")
