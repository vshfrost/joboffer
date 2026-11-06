"""Одноразові посилання на PDF документів: `document_download_links` (лише sha256-дайджест токена).

Revision ID: 0032
Revises: 0031
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_download_links",
        sa.Column("token_digest", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_download_links_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_document_download_links_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "token_digest", name=op.f("pk_document_download_links")
        ),
    )
    op.create_index(
        op.f("ix_document_download_links_document_id"),
        "document_download_links",
        ["document_id"],
    )
    op.create_index(
        op.f("ix_document_download_links_user_id"),
        "document_download_links",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_table("document_download_links")
