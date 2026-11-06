"""Фото для шапки CV: `photos` (UUID + номер на користувача, JPEG у `bytea`), лічильник номерів
`photo_counters` і `documents.photo_id` (FK `ON DELETE SET NULL`: видалене фото не чіпає документи).

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "photos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("photo_number", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "photo_number >= 1", name=op.f("ck_photos_photo_number_positive")
        ),
        sa.CheckConstraint(
            "width >= 1 AND height >= 1", name=op.f("ck_photos_size_positive")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_photos_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_photos")),
        sa.UniqueConstraint(
            "user_id", "photo_number", name=op.f("uq_photos_user_id_photo_number")
        ),
    )
    op.create_table(
        "photo_counters",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "last_number >= 0", name=op.f("ck_photo_counters_last_number_valid")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_photo_counters_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_photo_counters")),
    )
    op.add_column("documents", sa.Column("photo_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_documents_photo_id_photos"),
        "documents",
        "photos",
        ["photo_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_documents_photo_id"), "documents", ["photo_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_documents_photo_id"), table_name="documents")
    op.drop_constraint(
        op.f("fk_documents_photo_id_photos"), "documents", type_="foreignkey"
    )
    op.drop_column("documents", "photo_id")
    op.drop_table("photo_counters")
    op.drop_table("photos")
