"""Теми підготовки до інтерв'ю: `prep_topics` (UUID + номер на користувача, slug унікальний у
межах користувача), лічильник номерів `prep_topic_counters` і прив'язки до вакансій
`prep_topic_jobs` (тема + вакансія → прогалина).

Revision ID: 0020
Revises: 0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prep_topics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("topic_number", sa.Integer(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "topic_number >= 1", name=op.f("ck_prep_topics_topic_number_positive")
        ),
        sa.CheckConstraint(
            "kind IN ('tech', 'behavioral', 'domain')",
            name=op.f("ck_prep_topics_kind_known"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_prep_topics_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prep_topics")),
        sa.UniqueConstraint(
            "user_id", "slug", name=op.f("uq_prep_topics_user_id_slug")
        ),
        sa.UniqueConstraint(
            "user_id",
            "topic_number",
            name=op.f("uq_prep_topics_user_id_topic_number"),
        ),
    )
    op.create_table(
        "prep_topic_counters",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "last_number >= 0", name=op.f("ck_prep_topic_counters_last_number_valid")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_prep_topic_counters_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_prep_topic_counters")),
    )
    op.create_table(
        "prep_topic_jobs",
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("gap", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_prep_topic_jobs_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["prep_topics.id"],
            name=op.f("fk_prep_topic_jobs_topic_id_prep_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("topic_id", "job_id", name=op.f("pk_prep_topic_jobs")),
    )
    op.create_index("ix_prep_topic_jobs_job_id", "prep_topic_jobs", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_prep_topic_jobs_job_id", table_name="prep_topic_jobs")
    op.drop_table("prep_topic_jobs")
    op.drop_table("prep_topic_counters")
    op.drop_table("prep_topics")
