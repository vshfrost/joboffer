"""Результати контексту agents: примітиви."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentData:
    id: str
    kind: str
    name: str
