"""Порт хешування паролів. Домен сирого пароля не бачить: хеш і перевірку робить адаптер."""

from typing import Protocol

from domain.identity.password import PasswordHash


class PasswordHasher(Protocol):
    async def hash(self, raw: str) -> PasswordHash:
        """Новий хеш із власною сіллю: той самий пароль двічі дає різні хеші."""
        ...

    async def verify(self, raw: str, stored: PasswordHash | None) -> bool:
        """`stored=None` (користувача нема) витрачає стільки ж часу, що й справжня перевірка, і дає `False`.

        Зіпсований `stored` теж дає `False`, а не виняток.
        """
        ...
