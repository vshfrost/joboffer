"""OAuth: DCR-клієнти, гранти користувачів, коди й токени (лише дайджести).

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("redirect_uris", postgresql.JSONB(), nullable=False),
        sa.Column("registration", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_clients")),
    )
    op.create_table(
        "oauth_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_oauth_grants_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["oauth_clients.id"],
            name=op.f("fk_oauth_grants_client_id_oauth_clients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_grants")),
    )
    op.create_index(op.f("ix_oauth_grants_user_id"), "oauth_grants", ["user_id"])
    op.create_index(op.f("ix_oauth_grants_client_id"), "oauth_grants", ["client_id"])
    op.create_table(
        "oauth_tokens",
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("grant_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code_challenge", sa.Text(), nullable=True),
        sa.Column("redirect_uri", sa.Text(), nullable=True),
        sa.Column("redirect_uri_provided_explicitly", sa.Boolean(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('code', 'access', 'refresh')", name=op.f("ck_oauth_tokens_kind")
        ),
        sa.ForeignKeyConstraint(
            ["grant_id"],
            ["oauth_grants.id"],
            name=op.f("fk_oauth_tokens_grant_id_oauth_grants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("digest", name=op.f("pk_oauth_tokens")),
    )
    op.create_index(op.f("ix_oauth_tokens_grant_id"), "oauth_tokens", ["grant_id"])
    op.create_index(op.f("ix_oauth_tokens_expires_at"), "oauth_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_table("oauth_tokens")
    op.drop_table("oauth_grants")
    op.drop_table("oauth_clients")
