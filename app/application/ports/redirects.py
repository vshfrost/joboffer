"""Порт політики адрес повернення: що з redirect_uri дозволено клієнту. Розбір URI — справа адаптера."""

from typing import Protocol


class RedirectPolicy(Protocol):
    def allows(self, uri: str) -> bool: ...

    def host(self, uri: str) -> str:
        """Хост адреси для екрана згоди; `?`, якщо його нема."""
        ...
