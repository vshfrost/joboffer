"""Агенти користувача: `user_agents` — один рядок на (користувач, OAuth-клієнт).

Наповнюється з грантів, що діють на момент міграції (не відкликані, з невикористаним і непрострочаним
refresh-токеном); вид і назву дає `classify_agent`, агент привʼязується до найновішого такого гранту.

Revision ID: 0029
Revises: 0028
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, distinct_on

from domain.agents.classification import classify_agent

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("grant_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_agents_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["oauth_clients.id"],
            name=op.f("fk_user_agents_client_id_oauth_clients"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["grant_id"],
            ["oauth_grants.id"],
            name=op.f("fk_user_agents_grant_id_oauth_grants"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_agents")),
        sa.UniqueConstraint(
            "user_id", "client_id", name=op.f("uq_user_agents_user_id")
        ),
    )
    _backfill()


def _backfill() -> None:
    connection = op.get_bind()
    grants = sa.table(
        "oauth_grants",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("client_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("revoked_at", sa.DateTime(timezone=True)),
    )
    clients = sa.table(
        "oauth_clients",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.Text()),
        sa.column("redirect_uris", JSONB()),
    )
    tokens = sa.table(
        "oauth_tokens",
        sa.column("grant_id", sa.Uuid()),
        sa.column("kind", sa.String()),
        sa.column("expires_at", sa.DateTime(timezone=True)),
        sa.column("consumed_at", sa.DateTime(timezone=True)),
    )
    live_refresh = sa.exists().where(
        tokens.c.grant_id == grants.c.id,
        tokens.c.kind == "refresh",
        tokens.c.consumed_at.is_(None),
        tokens.c.expires_at > sa.func.now(),
    )
    newest_live = (
        sa.select(
            grants.c.id,
            grants.c.user_id,
            grants.c.client_id,
            grants.c.created_at,
            clients.c.name,
            clients.c.redirect_uris,
        )
        .select_from(grants.join(clients, clients.c.id == grants.c.client_id))
        .where(grants.c.revoked_at.is_(None), live_refresh)
        .ext(distinct_on(grants.c.user_id, grants.c.client_id))
        .order_by(grants.c.user_id, grants.c.client_id, grants.c.created_at.desc())
    )
    live = connection.execute(newest_live).all()
    agents = sa.table(
        "user_agents",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("client_id", sa.Uuid()),
        sa.column("grant_id", sa.Uuid()),
        sa.column("kind", sa.String()),
        sa.column("name", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    rows = []
    for grant_id, user_id, client_id, created_at, name, redirect_uris in live:
        identity = classify_agent(str(client_id), name, tuple(redirect_uris))
        rows.append(
            {
                "id": uuid4(),
                "user_id": user_id,
                "client_id": client_id,
                "grant_id": grant_id,
                "kind": identity.kind.value,
                "name": identity.name,
                "created_at": created_at,
            }
        )
    if rows:
        op.bulk_insert(agents, rows)


def downgrade() -> None:
    op.drop_table("user_agents")
