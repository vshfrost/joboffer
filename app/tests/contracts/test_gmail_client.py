"""Gmail API через httpx2 MockTransport і фейковий токен-ендпоінт Google: без мережі."""

import base64
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest
from anyio.from_thread import BlockingPortal

from application.ports.mail import Mailbox
from domain.mail.mail import CursorExpired, MailboxError
from infrastructure.gmail.client import (
    API_URL,
    GMAIL_SCOPE,
    OAUTH_URL,
    PAGE_SIZE,
    GmailCredentials,
    GmailMailbox,
    connect,
)

FIXTURES = Path(__file__).parent / "gmail_fixtures"
FAKE_SECRET = "client-secret"  # фейкові креди, мережі в тестах нема
FAKE_REFRESH = "refresh-token"
type Handler = Callable[[httpx2.Request], httpx2.Response]


class TokenEndpoint:
    """Фейковий https://oauth2.googleapis.com/token: щоразу новий access token."""

    def __init__(self, *, status: int = 200) -> None:
        self.status = status
        self.requests: list[httpx2.Request] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx2.Response(self.status, json={"error": "invalid_grant"})
        return httpx2.Response(
            200,
            json={
                "access_token": f"access-{self.calls}",
                "expires_in": 3599,
                "scope": GMAIL_SCOPE,
                "token_type": "Bearer",
            },
        )


def mailbox(
    handler: Handler,
    *,
    endpoint: TokenEndpoint | None = None,
    clock: Callable[[], float] = lambda: 0.0,
) -> GmailMailbox:
    token_endpoint = endpoint or TokenEndpoint()

    def route(request: httpx2.Request) -> httpx2.Response:
        if str(request.url) == OAUTH_URL:
            return token_endpoint(request)
        return handler(request)

    http = httpx2.AsyncClient(base_url=API_URL, transport=httpx2.MockTransport(route))
    creds = GmailCredentials(
        client_id="id", client_secret=FAKE_SECRET, refresh_token=FAKE_REFRESH
    )
    return GmailMailbox(creds, http, clock)


def ok(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, json={"emailAddress": "a@b.c", "historyId": "1"})


def raw_message(message_id: str = "m1") -> dict[str, Any]:
    raw = (FIXTURES / "reply.eml").read_bytes()
    return {
        "id": message_id,
        "internalDate": "1791879360000",
        # Gmail віддає base64url без доповнення «=».
        "raw": base64.urlsafe_b64encode(raw).decode().rstrip("="),
    }


def test_gmail_mailbox_is_a_mailbox() -> None:
    port: Mailbox = mailbox(ok)

    assert isinstance(port, GmailMailbox)


def test_profile_gives_lowercase_address_and_cursor(portal: BlockingPortal) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/gmail/v1/users/me/profile"
        assert request.headers["authorization"] == "Bearer access-1"
        return httpx2.Response(
            200, json={"emailAddress": "Mailroom@Example.com", "historyId": 42}
        )

    box = mailbox(handler)

    assert portal.call(box.profile).address == "mailroom@example.com"
    assert portal.call(box.profile_cursor) == "42"


def test_changes_walk_all_pages_and_drop_repeated_messages(
    portal: BlockingPortal,
) -> None:
    pages = {
        "": {
            "history": [
                {"id": "11", "messagesAdded": [{"message": {"id": "a"}}]},
                {"id": "12", "messages": [{"id": "x"}]},  # не messageAdded
            ],
            "nextPageToken": "p2",
            "historyId": "12",
        },
        "p2": {
            "history": [
                {
                    "id": "13",
                    "messagesAdded": [
                        {"message": {"id": "b"}},
                        {"message": {"id": "a"}},
                    ],
                }
            ],
            "historyId": "14",
        },
    }
    seen: list[dict[str, str]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/gmail/v1/users/me/history"
        params = dict(request.url.params)
        seen.append(params)
        return httpx2.Response(200, json=pages[params.get("pageToken", "")])

    changes = portal.call(mailbox(handler).changes, "10")

    assert changes.message_ids == ("a", "b")
    assert changes.cursor == "14"
    assert seen[0] == {
        "startHistoryId": "10",
        "historyTypes": "messageAdded",
        "maxResults": str(PAGE_SIZE),
    }
    assert seen[1]["pageToken"] == "p2"


def test_no_changes_keep_the_mailbox_cursor(portal: BlockingPortal) -> None:
    box = mailbox(lambda request: httpx2.Response(200, json={"historyId": "20"}))

    changes = portal.call(box.changes, "10")

    assert changes.message_ids == ()
    assert changes.cursor == "20"


def test_expired_cursor_raises_cursor_expired(portal: BlockingPortal) -> None:
    box = mailbox(lambda request: httpx2.Response(404, json={}))

    with pytest.raises(CursorExpired):
        portal.call(box.changes, "1")


def test_since_searches_spam_and_trash_and_returns_oldest_first(
    portal: BlockingPortal,
) -> None:
    pages = {
        "": {"messages": [{"id": "c"}, {"id": "b"}], "nextPageToken": "p2"},
        "p2": {"messages": [{"id": "a"}]},
    }
    seen: list[dict[str, str]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/gmail/v1/users/me/messages"
        params = dict(request.url.params)
        seen.append(params)
        return httpx2.Response(200, json=pages[params.get("pageToken", "")])

    ids = portal.call(mailbox(handler).since, datetime(2026, 7, 16, tzinfo=UTC))

    assert ids == ["a", "b", "c"]
    assert seen[0]["q"] == "after:1784160000"
    assert seen[0]["includeSpamTrash"] == "true"


def test_since_without_messages_is_empty(portal: BlockingPortal) -> None:
    box = mailbox(lambda request: httpx2.Response(200, json={"resultSizeEstimate": 0}))

    assert portal.call(box.since, datetime(2026, 7, 16, tzinfo=UTC)) == []


def test_message_is_fetched_raw_and_parsed(portal: BlockingPortal) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/gmail/v1/users/me/messages/m1"
        assert request.url.params["format"] == "raw"
        return httpx2.Response(200, json=raw_message())

    mail = portal.call(mailbox(handler).message, "m1")

    assert mail is not None
    assert mail.id == "m1"
    assert mail.received_at == datetime(2026, 10, 13, 8, 16, tzinfo=UTC)
    assert mail.from_address == "talent@acme.example"


def test_missing_message_is_none(portal: BlockingPortal) -> None:
    box = mailbox(lambda request: httpx2.Response(404, json={}))

    assert portal.call(box.message, "gone") is None


def test_api_error_raises_mailbox_error_with_status(portal: BlockingPortal) -> None:
    box = mailbox(lambda request: httpx2.Response(500, json={}))

    with pytest.raises(MailboxError, match="500 на profile"):
        portal.call(box.profile)


def test_network_error_raises_mailbox_error(portal: BlockingPortal) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("down", request=request)

    with pytest.raises(MailboxError, match="ConnectError"):
        portal.call(mailbox(handler).profile)


def test_the_first_call_gets_an_access_token_from_the_refresh_token(
    portal: BlockingPortal,
) -> None:
    endpoint = TokenEndpoint()
    tokens: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        tokens.append(request.headers["authorization"])
        return ok(request)

    portal.call(mailbox(handler, endpoint=endpoint).profile)

    assert endpoint.calls == 1
    assert tokens == ["Bearer access-1"]
    form = dict(
        pair.split("=") for pair in endpoint.requests[0].content.decode().split("&")
    )
    assert form == {
        "grant_type": "refresh_token",
        "client_id": "id",
        "client_secret": FAKE_SECRET,
        "refresh_token": FAKE_REFRESH,
    }


def test_the_token_is_reused_until_it_expires(portal: BlockingPortal) -> None:
    endpoint = TokenEndpoint()
    now = [0.0]
    tokens: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        tokens.append(request.headers["authorization"])
        return ok(request)

    box = mailbox(handler, endpoint=endpoint, clock=lambda: now[0])

    portal.call(box.profile)
    now[0] = 3000.0
    portal.call(box.profile)
    now[0] = 3600.0  # expires_in 3599 — токен уже протух
    portal.call(box.profile)

    assert tokens == ["Bearer access-1", "Bearer access-1", "Bearer access-2"]
    assert endpoint.calls == 2


def test_rejected_token_is_refreshed_once_and_the_call_repeated(
    portal: BlockingPortal,
) -> None:
    endpoint = TokenEndpoint()
    tokens: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        tokens.append(request.headers["authorization"])
        if len(tokens) == 1:
            return httpx2.Response(401, json={})
        return ok(request)

    portal.call(mailbox(handler, endpoint=endpoint).profile)

    assert tokens == ["Bearer access-1", "Bearer access-2"]
    assert endpoint.calls == 2


def test_still_rejected_token_is_not_retried_again(portal: BlockingPortal) -> None:
    endpoint = TokenEndpoint()
    box = mailbox(lambda request: httpx2.Response(401, json={}), endpoint=endpoint)

    with pytest.raises(MailboxError, match="401"):
        portal.call(box.profile)
    assert endpoint.calls == 2


def test_revoked_refresh_token_raises_mailbox_error_without_secrets(
    portal: BlockingPortal,
) -> None:
    box = mailbox(ok, endpoint=TokenEndpoint(status=400))

    with pytest.raises(MailboxError, match="refresh token") as caught:
        portal.call(box.profile)
    assert FAKE_SECRET not in str(caught.value)
    assert FAKE_REFRESH not in str(caught.value)


def test_token_endpoint_network_error_raises_mailbox_error(
    portal: BlockingPortal,
) -> None:
    def route(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("down", request=request)

    http = httpx2.AsyncClient(base_url=API_URL, transport=httpx2.MockTransport(route))
    creds = GmailCredentials("id", FAKE_SECRET, FAKE_REFRESH)

    with pytest.raises(MailboxError, match="ConnectError"):
        portal.call(GmailMailbox(creds, http).profile)


def test_connect_builds_a_mailbox_without_network(portal: BlockingPortal) -> None:
    creds = GmailCredentials("id", FAKE_SECRET, FAKE_REFRESH)

    box = connect(creds)
    portal.call(box.aclose)

    assert isinstance(box, GmailMailbox)
    assert FAKE_SECRET not in repr(creds)
    assert FAKE_REFRESH not in repr(creds)
