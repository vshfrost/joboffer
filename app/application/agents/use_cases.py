"""Use cases агентів: список підключених агентів поточного користувача."""

from collections.abc import Callable

from application.contracts.actor import Actor
from application.contracts.agents import AgentData
from application.ports.agents import AgentsUnitOfWork
from application.ports.clock import Clock


class AgentUseCases:
    def __init__(
        self, unit_of_work: Callable[[], AgentsUnitOfWork], clock: Clock
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def list_agents(self, actor: Actor) -> tuple[AgentData, ...]:
        """Лише агенти, чий грант живий саме зараз."""
        async with self._unit_of_work() as uow:
            agents = await uow.user_agents.connected(actor.user_id, self._clock.now())
        return tuple(
            AgentData(id=str(a.id), kind=a.kind.value, name=a.name) for a in agents
        )
