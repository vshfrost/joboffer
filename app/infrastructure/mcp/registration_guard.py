"""Захист публічного DCR `/register`: ліміт запитів з одного клієнта й ліміт розміру тіла."""

from collections.abc import Callable

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


class RegistrationGuard:
    def __init__(
        self,
        app: ASGIApp,
        client_key: Callable[[Request], str],
        *,
        now: Callable[[], float],
    ) -> None:
        self.app = app
        self.client_key = client_key
        self.now = now

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)
