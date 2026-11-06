"""Захист публічного DCR `/register`: ліміт запитів з одного клієнта й ліміт розміру тіла.

DCR відкритий без автентифікації й кожен успішний запит додає рядок у базу. Ліміт веде процес агента
у памʼяті (агент — один процес): після перезапуску лічильники з нуля, а межа лишається годинною.
Рахується кожен POST, зокрема відхилений за розміром. Чистий ASGI: тіло не читається, поки клієнт
не вкладеться в ліміт; до SDK воно доходить без змін.
"""

import math
from collections import deque
from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY = 16 * 1024
REGISTER_LIMIT = 10
REGISTER_WINDOW = 3600.0
# Скільки клієнтів тримати в памʼяті: понад це прострочені записи вичищаються одразу.
MAX_TRACKED_CLIENTS = 4096


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
        self._hits: dict[str, deque[float]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not (
            scope["type"] == "http"
            and scope["path"] == "/register"
            and scope["method"] == "POST"
        ):
            await self.app(scope, receive, send)
            return
        retry_after = self._hit(self.client_key(Request(scope)))
        if retry_after is not None:
            await JSONResponse(
                {"error": "rate_limited"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )(scope, receive, send)
            return
        replay = await _bounded_body(scope, receive)
        if replay is None:
            await JSONResponse({"error": "invalid_client_metadata"}, status_code=413)(
                scope, receive, send
            )
            return
        await self.app(scope, replay, send)

    def _hit(self, client: str) -> int | None:
        """Записує спробу; `None` — пропустити, число — через скільки секунд можна знову."""
        now = self.now()
        if len(self._hits) > MAX_TRACKED_CLIENTS:
            self._hits = {
                key: hits
                for key, hits in self._hits.items()
                if hits and hits[-1] > now - REGISTER_WINDOW
            }
        hits = self._hits.setdefault(client, deque())
        while hits and hits[0] <= now - REGISTER_WINDOW:
            hits.popleft()
        if len(hits) >= REGISTER_LIMIT:
            return max(1, math.ceil(hits[0] + REGISTER_WINDOW - now))
        hits.append(now)
        return None


async def _bounded_body(scope: Scope, receive: Receive) -> Receive | None:
    """Тіло до `MAX_BODY` байтів, відтворене для вкладеного застосунку; `None` — завелике."""
    for name, value in scope["headers"]:
        if name == b"content-length" and value.isdigit() and int(value) > MAX_BODY:
            return None
    messages: list[Message] = []
    size = 0
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] != "http.request":
            break
        size += len(message.get("body", b""))
        if size > MAX_BODY:
            return None
        if not message.get("more_body", False):
            break

    async def replay() -> Message:
        return messages.pop(0) if messages else await receive()

    return replay
