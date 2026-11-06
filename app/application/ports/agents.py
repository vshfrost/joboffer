"""Порти контексту agents: агенти користувача й unit of work для їхнього списку."""

from datetime import datetime
from typing import Protocol

from application.ports.unit_of_work import UnitOfWork
from domain.agents.agent import UserAgent
from domain.identity.ids import UserId


class AgentRegistry(Protocol):
    """Запис агентів: ним користується OAuth, коли користувач дає клієнту грант."""

    async def upsert(self, agent: UserAgent) -> None:
        """Один рядок на (користувач, клієнт): повторне підключення лише зсуває `grant_id` на новіший."""
        ...


class AgentListing(Protocol):
    async def connected(self, user_id: UserId, now: datetime) -> list[UserAgent]:
        """Агенти користувача з живим грантом (правило `Grants.has_live`), за часом першого підключення."""
        ...


class AgentsUnitOfWork(UnitOfWork, Protocol):
    @property
    def user_agents(self) -> AgentListing: ...
