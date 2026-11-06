"""Correlation ID запиту: з заголовка клієнта, якщо він безпечний, інакше новий.

Зберігається в `request.state.correlation_id` (для тіл помилок і логів) і повертається
в заголовку відповіді. Це операційна мітка, а не авторизація.
"""

import re
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Correlation-ID"
# Лише короткі безпечні значення: заголовок потрапляє в логи й відповіді.
_SAFE = re.compile(r"[A-Za-z0-9._-]{1,64}")


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        incoming = Headers(scope=scope).get(HEADER, "")
        value = incoming if _SAFE.fullmatch(incoming) else uuid4().hex
        scope.setdefault("state", {})["correlation_id"] = value

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append(HEADER, value)
            await send(message)

        await self._app(scope, receive, send_with_header)


def correlation_id(request: Request) -> str:
    value = getattr(request.state, "correlation_id", "")
    return value if isinstance(value, str) else ""
