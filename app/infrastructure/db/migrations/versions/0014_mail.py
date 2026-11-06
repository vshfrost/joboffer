"""Пошта: особисті адреси (`mail_inboxes`, `mail_retired_tags`), стан синку Gmail
(`mail_sync_state`), листи (`mail_messages`) і відкинуті листи без тексту (`mail_dropped`).
Колонки листів і адрес збігаються з v1 — ETL у B12 переносить їх без втрат.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> sa.TextClause:
    return sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "mail_inboxes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_now(),
            nullable=False,
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_mail_inboxes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_mail_inboxes")),
        sa.UniqueConstraint("tag", name=op.f("uq_mail_inboxes_tag")),
    )
    op.create_table(
        "mail_retired_tags",
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "retired_at",
            sa.DateTime(timezone=True),
            server_default=_now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_mail_retired_tags_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tag", name=op.f("pk_mail_retired_tags")),
    )
    op.create_table(
        "mail_sync_state",
        sa.Column("mailbox", sa.Text(), nullable=False),
        sa.Column("history_id", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), server_default="", nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("mailbox", name=op.f("pk_mail_sync_state")),
    )
    op.create_table(
        "mail_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("gmail_id", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Text(), server_default="", nullable=False),
        sa.Column("in_reply_to", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "reference_ids",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("from_address", sa.Text(), server_default="", nullable=False),
        sa.Column("from_name", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "to_addresses",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("subject", sa.Text(), server_default="", nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("sender_auth", sa.Text(), server_default="unknown", nullable=False),
        sa.Column("untrusted_text", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "attachments", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("parse_error", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('company', 'linkedin_alert', 'linkedin_application', "
            "'linkedin_message', 'forwarding_confirmation', 'suspicious', 'other')",
            name=op.f("ck_mail_messages_category_known"),
        ),
        sa.CheckConstraint(
            "sender_auth IN ('verified', 'failed', 'unknown')",
            name=op.f("ck_mail_messages_sender_auth_known"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_mail_messages_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mail_messages")),
        sa.UniqueConstraint("gmail_id", name=op.f("uq_mail_messages_gmail_id")),
    )
    op.create_index(
        "ix_mail_messages_user_id_received_at",
        "mail_messages",
        ["user_id", "received_at"],
    )
    op.create_table(
        "mail_dropped",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("gmail_id", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("from_address", sa.Text(), server_default="", nullable=False),
        sa.Column("subject", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reason IN ('daily_limit', 'retired_tag')",
            name=op.f("ck_mail_dropped_reason_known"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_mail_dropped_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mail_dropped")),
        sa.UniqueConstraint("gmail_id", name=op.f("uq_mail_dropped_gmail_id")),
    )
    op.create_index(
        "ix_mail_dropped_user_id_reason_received_at",
        "mail_dropped",
        ["user_id", "reason", "received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mail_dropped_user_id_reason_received_at", table_name="mail_dropped"
    )
    op.drop_table("mail_dropped")
    op.drop_index("ix_mail_messages_user_id_received_at", table_name="mail_messages")
    op.drop_table("mail_messages")
    op.drop_table("mail_sync_state")
    op.drop_table("mail_retired_tags")
    op.drop_table("mail_inboxes")
