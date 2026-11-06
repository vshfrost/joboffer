"""UserAgents на Postgres. «Підключений» = у користувача є живий грант цього клієнта (правило `live_grants`)."""

from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.agents.agent import AgentKind, UserAgent
from domain.agents.ids import AgentId
from domain.identity.ids import GrantId, UserId
from domain.oauth.ids import ClientId
from infrastructure.db.agents.tables import UserAgentRow
from infrastructure.db.oauth.repository import live_grants
from infrastructure.db.oauth.tables import OAuthGrantRow


def _to_domain(row: UserAgentRow) -> UserAgent:
    return UserAgent(
        id=AgentId(row.id),
        user_id=UserId(row.user_id),
        client_id=ClientId(row.client_id),
        grant_id=None if row.grant_id is None else GrantId(row.grant_id),
        kind=AgentKind(row.kind),
        name=row.name,
        created_at=row.created_at,
    )


class PostgresUserAgents:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, agent: UserAgent) -> None:
        insert = pg_insert(UserAgentRow).values(
            id=agent.id.value,
            user_id=agent.user_id.value,
            client_id=agent.client_id.value,
            grant_id=None if agent.grant_id is None else agent.grant_id.value,
            kind=agent.kind.value,
            name=agent.name,
            created_at=agent.created_at,
        )
        await self._session.execute(
            insert.on_conflict_do_update(
                index_elements=[UserAgentRow.user_id, UserAgentRow.client_id],
                set_={"grant_id": insert.excluded.grant_id},
            )
        )

    async def connected(self, user_id: UserId, now: datetime) -> list[UserAgent]:
        has_live_grant = exists(
            live_grants(now).where(
                OAuthGrantRow.user_id == UserAgentRow.user_id,
                OAuthGrantRow.client_id == UserAgentRow.client_id,
            )
        )
        rows = await self._session.scalars(
            select(UserAgentRow)
            .where(UserAgentRow.user_id == user_id.value, has_live_grant)
            .order_by(UserAgentRow.created_at, UserAgentRow.id)
        )
        return [_to_domain(row) for row in rows]
