"""ResourceGuard на сирому ASGI: відтворення тіла, відмови за розміром і кодуванням, обрив з'єднання."""

from typing import Any, cast
from urllib.parse import urlencode

import pytest
from starlette.types import Message, Receive, Scope, Send

from infrastructure.mcp.resource_guard import MAX_BODY, ResourceGuard

pytestmark = pytest.mark.anyio

RESOURCE = "https://agent.example/joboffer"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Recorder:
    """Вкладений застосунок: що він побачив і що відповів."""

    def __init__(self) -> None:
        self.body = b""
        self.called = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.called = True
        while True:
            message = await receive()
            self.body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


async def call(
    inner: Recorder,
    chunks: list[bytes],
    *,
    path: str = "/token",
    disconnect_first: bool = False,
) -> list[Message]:
    queue: list[Message] = (
        [{"type": "http.disconnect"}]
        if disconnect_first
        else [
            {
                "type": "http.request",
                "body": chunk,
                "more_body": index < len(chunks) - 1,
            }
            for index, chunk in enumerate(chunks)
        ]
    )
    sent: list[Message] = []

    async def receive() -> Message:
        return queue.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    scope = cast(Scope, {"type": "http", "path": path, "method": "POST", "headers": []})
    await ResourceGuard(inner, RESOURCE)(scope, receive, send)
    return sent


def status(sent: list[Message]) -> int:
    return int(cast(dict[str, Any], sent[0])["status"])


async def test_body_split_into_chunks_reaches_the_app_unchanged() -> None:
    inner = Recorder()
    body = urlencode(
        {"grant_type": "authorization_code", "resource": RESOURCE}
    ).encode()

    sent = await call(inner, [body[:10], body[10:]])

    assert status(sent) == 204
    assert inner.body == body


async def test_other_paths_pass_through_untouched() -> None:
    inner = Recorder()

    sent = await call(inner, [b"resource=https%3A%2F%2Fevil.example"], path="/register")

    assert status(sent) == 204
    assert inner.called


async def test_body_that_is_not_utf8_is_invalid_request() -> None:
    inner = Recorder()

    sent = await call(inner, [b"\xff\xfe=\x80"])

    assert status(sent) == 400
    assert not inner.called


async def test_body_over_the_limit_in_chunks_is_413_and_never_reaches_the_app() -> None:
    inner = Recorder()

    sent = await call(inner, [b"a=" + b"x" * MAX_BODY, b"y"])

    assert status(sent) == 413
    assert not inner.called


async def test_client_that_disconnects_gets_no_response() -> None:
    inner = Recorder()

    sent = await call(inner, [], disconnect_first=True)

    assert sent == []
    assert not inner.called
