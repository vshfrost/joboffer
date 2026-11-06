"""Перевірка `resource` у запитах /token (SDK її там не робить).

Чистий ASGI: тіло відтворюється для SDK без змін (автентифікація клієнта, PKCE).
Caddy стрипить зовнішній префікс перед /token.
"""

from urllib.parse import parse_qs

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY = 65536
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class ResourceGuard:
    def __init__(self, app: ASGIApp, resource: str) -> None:
        self.app = app
        self.resource = resource

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not (
            scope["type"] == "http"
            and scope["path"] == "/token"
            and scope["method"] == "POST"
        ):
            await self.app(scope, receive, send)
            return
        messages: list[Message] = []
        body = bytearray()
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_BODY:
                await JSONResponse({"error": "invalid_request"}, status_code=413)(
                    scope, receive, send
                )
                return
            if not message.get("more_body", False):
                break
        try:
            form = parse_qs(body.decode(), keep_blank_values=True)
        except UnicodeDecodeError:
            await JSONResponse({"error": "invalid_request"}, status_code=400)(
                scope, receive, send
            )
            return
        resources = form.get("resource")
        if resources is not None and resources != [self.resource]:
            await JSONResponse(
                {"error": "invalid_target"}, status_code=400, headers=_NO_STORE
            )(scope, receive, send)
            return

        async def replay() -> Message:
            return messages.pop(0) if messages else await receive()

        await self.app(scope, replay, send)
