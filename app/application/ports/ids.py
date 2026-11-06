"""Порт ID: нові UUID генерує адаптер (uuid4 у системі, лічильник у тестах), не домен."""

from typing import Protocol
from uuid import UUID


class IdGenerator(Protocol):
    def new(self) -> UUID: ...
