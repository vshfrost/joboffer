"""Джерела вакансій (B10): компанії ATS і RSS-стрічки користувачів та стан їх останнього прогону.

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ERROR_KNOWN = (
    "error IS NULL OR error IN ('timeout', 'not_found', 'rate_limited', 'unavailable', "
    "'rejected', 'invalid', 'unsupported')"
)


def _run_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("found", sa.Integer(), nullable=False),
        sa.Column("imported", sa.Integer(), nullable=False),
        sa.Column("filtered", sa.Integer(), nullable=False),
        sa.Column("duplicate", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "source_companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_source_companies_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_companies")),
        sa.UniqueConstraint(
            "user_id",
            "platform",
            "slug",
            name=op.f("uq_source_companies_user_id_platform_slug"),
        ),
        sa.CheckConstraint(
            "platform IN ('greenhouse', 'ashby', 'lever')",
            name=op.f("ck_source_companies_platform_known"),
        ),
    )
    op.create_table(
        "source_feeds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_source_feeds_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_feeds")),
        sa.UniqueConstraint(
            "user_id",
            "source",
            "query",
            name=op.f("uq_source_feeds_user_id_source_query"),
        ),
        sa.CheckConstraint(
            "source IN ('dou', 'djinni')", name=op.f("ck_source_feeds_source_known")
        ),
    )
    op.create_table(
        "source_company_runs",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        *_run_columns(),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["source_companies.id"],
            name=op.f("fk_source_company_runs_company_id_source_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("company_id", name=op.f("pk_source_company_runs")),
        sa.CheckConstraint(
            ERROR_KNOWN, name=op.f("ck_source_company_runs_error_known")
        ),
    )
    op.create_table(
        "source_feed_runs",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        *_run_columns(),
        sa.ForeignKeyConstraint(
            ["feed_id"],
            ["source_feeds.id"],
            name=op.f("fk_source_feed_runs_feed_id_source_feeds"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("feed_id", name=op.f("pk_source_feed_runs")),
        sa.CheckConstraint(ERROR_KNOWN, name=op.f("ck_source_feed_runs_error_known")),
    )


def downgrade() -> None:
    op.drop_table("source_feed_runs")
    op.drop_table("source_company_runs")
    op.drop_table("source_feeds")
    op.drop_table("source_companies")
