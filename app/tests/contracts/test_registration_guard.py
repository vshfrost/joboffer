"""RegistrationGuard на сирому ASGI: ліміт реєстрацій з клієнта, ліміт розміру тіла, прозорий пропуск решти."""

from typing import Any, cast

import pytest
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

from infrastructure.mcp.registration_guard import RegistrationGuard

pytestmark = pytest.mark.anyio

HOUR = 3600.0
DCR = b'{"client_name":"Claude","redirect_uris":["https://claude.ai/api/mcp/auth_callback"]}'


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Recorder:
    """Вкладений застосунок: скільки разів його викликали і які тіла він прочитав."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.calls += 1
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 201, "headers": []})
        await send({"type": "http.response.body", "body": b""})


class Clock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value


def client_of(request: Request) -> str:
    return request.headers.get("x-client", "10.0.0.1")


def guard(inner: Recorder, clock: Clock) -> RegistrationGuard:
    return RegistrationGuard(inner, client_of, now=clock)


async def post(
    app: RegistrationGuard,
    chunks: list[bytes],
    *,
    path: str = "/register",
    method: str = "POST",
    client: str = "10.0.0.1",
    content_length: int | None = None,
) -> tuple[int, dict[str, str]]:
    queue: list[Message] = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks or [b""])
    ]
    sent: list[Message] = []
    headers = [(b"x-client", client.encode())]
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))

    async def receive() -> Message:
        return queue.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    scope = cast(
        Scope,
        {"type": "http", "path": path, "method": method, "headers": headers},
    )
    await app(scope, receive, send)
    start = cast(dict[str, Any], sent[0])
    return start["status"], {k.decode(): v.decode() for k, v in start["headers"]}


async def test_registration_over_the_limit_is_refused_with_retry_after() -> None:
    inner, clock = Recorder(), Clock()
    app = guard(inner, clock)
    for _ in range(10):
        status, _ = await post(app, [DCR])
        assert status == 201

    status, headers = await post(app, [DCR])

    assert status == 429
    assert headers["retry-after"] == "3600"
    assert inner.calls == 10


async def test_other_client_is_not_limited_by_the_first_one() -> None:
    inner, clock = Recorder(), Clock()
    app = guard(inner, clock)
    for _ in range(10):
        await post(app, [DCR])

    status, _ = await post(app, [DCR], client="10.0.0.2")

    assert status == 201


async def test_registration_is_allowed_again_after_the_hour() -> None:
    inner, clock = Recorder(), Clock()
    app = guard(inner, clock)
    for _ in range(10):
        await post(app, [DCR])
    assert (await post(app, [DCR]))[0] == 429

    clock.value += HOUR + 1
    status, _ = await post(app, [DCR])

    assert status == 201


async def test_body_over_16_kib_is_refused_without_reaching_the_app() -> None:
    inner, clock = Recorder(), Clock()
    app = guard(inner, clock)

    status, _ = await post(app, [b"x" * 10_000, b"x" * 10_000])

    assert status == 413
    assert inner.calls == 0


async def test_declared_length_over_16_kib_is_refused_before_reading() -> None:
    inner, clock = Recorder(), Clock()
    app = guard(inner, clock)

    status, _ = await post(app, [], content_length=1_000_000)

    assert status == 413
    assert inner.calls == 0


async def test_refused_oversize_body_still_counts_towards_the_limit() -> None:
    inner, clock = Recorder(), Clock()
    app = guard(inner, clock)
    for _ in range(10):
        await post(app, [b"x" * 20_000])

    status, _ = await post(app, [DCR])

    assert status == 429


async def test_small_registration_reaches_the_app() -> None:
    inner, clock = Recorder(), Clock()

    status, _ = await post(guard(inner, clock), [DCR])

    assert (status, inner.calls) == (201, 1)


async def test_other_paths_and_methods_are_not_limited() -> None:
    inner, clock = Recorder(), Clock()
    app = guard(inner, clock)
    for _ in range(30):
        assert (await post(app, [b"a=1"], path="/token"))[0] == 201
        assert (await post(app, [], path="/register", method="OPTIONS"))[0] == 201
