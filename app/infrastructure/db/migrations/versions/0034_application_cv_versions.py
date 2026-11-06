"""Версія CV подачі: `application_cv_versions` (номер документа, день збереження, покриття слів).

Окрема таблиця, а не колонки `applications`: та лишається колонками v1 для ETL. Наявні подачі
рядка не мають, тож їхня версія «невідома».

Revision ID: 0034
Revises: 0033
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_cv_versions",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("cv_number", sa.Integer(), nullable=False),
        sa.Column("saved_on", sa.Date(), nullable=False),
        sa.Column("coverage_percent", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "cv_number >= 1", name=op.f("ck_application_cv_versions_cv_number_positive")
        ),
        sa.CheckConstraint(
            "coverage_percent BETWEEN 0 AND 100",
            name=op.f("ck_application_cv_versions_coverage_percent_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["applications.job_id"],
            name=op.f("fk_application_cv_versions_job_id_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_application_cv_versions")),
    )


def downgrade() -> None:
    op.drop_table("application_cv_versions")
