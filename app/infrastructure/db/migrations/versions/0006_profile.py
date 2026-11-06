"""Профіль пошуку роботи: `profiles` (один рядок на користувача) і `profile_locations`.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _list(name: str) -> sa.Column[list[str]]:
    return sa.Column(
        name,
        postgresql.ARRAY(sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'"),
    )


def _text(name: str) -> sa.Column[str]:
    return sa.Column(name, sa.Text(), nullable=False, server_default=sa.text("''"))


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        _list("roles"),
        _list("work_modes"),
        sa.Column(
            "include_unknown_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "relocation", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        _list("target_domains"),
        _list("seniority"),
        sa.Column("min_salary_eur", sa.Integer(), nullable=True),
        _list("stop_words"),
        _list("title_keywords"),
        _list("title_exclude"),
        _text("full_name"),
        _text("email"),
        _text("phone"),
        _text("linkedin_url"),
        _text("city"),
        _text("github_url"),
        _text("work_authorization"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "min_salary_eur >= 0", name=op.f("ck_profiles_min_salary_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_profiles")),
    )
    op.create_table(
        "profile_locations",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("place", sa.Text(), nullable=False),
        _list("aliases"),
        sa.Column("work_modes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.CheckConstraint(
            "cardinality(work_modes) > 0"
            " AND work_modes <@ ARRAY['remote', 'hybrid', 'onsite']",
            name=op.f("ck_profile_locations_work_modes_known"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_profile_locations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "position", name=op.f("pk_profile_locations")
        ),
    )
    op.create_index(
        "uq_profile_locations_user_id_place",
        "profile_locations",
        ["user_id", sa.text("lower(place)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("profile_locations")
    op.drop_table("profiles")
