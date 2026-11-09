"""Аналоги прогалин: `gap_analogues` у JSON розбору вакансії (`job_analyses.details`).

Наявні аналізи позначаються `null` — «без аналогів»: їх ніхто не оцінював, тож чесного «нема аналога» вони не
стверджують. Справжні аналоги з'являються після повторного аналізу вакансії. Код читає й без ключа
(`details.get`), міграція лише вирівнює дані.

Revision ID: 0037
Revises: 0036
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE job_analyses SET details = details || '{\"gap_analogues\": null}'::jsonb "
        "WHERE NOT details ? 'gap_analogues'"
    )


def downgrade() -> None:
    op.execute("UPDATE job_analyses SET details = details - 'gap_analogues'")
