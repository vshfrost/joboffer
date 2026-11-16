"""Платформи компаній у джерелах: до greenhouse, ashby, lever додаються smartrecruiters і workable.

Назад: компанії нових платформ видаляються (разом зі станом їхніх прогонів), обмеження повертається.

Revision ID: 0038
Revises: 0037
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_source_companies_platform_known"
OLD = "platform IN ('greenhouse', 'ashby', 'lever')"
NEW = "platform IN ('greenhouse', 'ashby', 'lever', 'smartrecruiters', 'workable')"


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "source_companies", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "source_companies", NEW)


def downgrade() -> None:
    op.execute(
        "DELETE FROM source_companies WHERE platform IN ('smartrecruiters', 'workable')"
    )
    op.drop_constraint(op.f(CONSTRAINT), "source_companies", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "source_companies", OLD)
