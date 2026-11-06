"""Що роботодавець просить від кандидатів: `candidate_asks` у JSON розбору вакансії (`job_analyses.details`).

Наявні аналізи отримують порожній список, тож читаються так само, як нові без прохань; справжні прохання
з'являються після повторного аналізу вакансії. Код читає й без ключа (`details.get`), міграція лише вирівнює дані.

Revision ID: 0036
Revises: 0035
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE job_analyses SET details = details || '{\"candidate_asks\": []}'::jsonb "
        "WHERE NOT details ? 'candidate_asks'"
    )


def downgrade() -> None:
    op.execute("UPDATE job_analyses SET details = details - 'candidate_asks'")
