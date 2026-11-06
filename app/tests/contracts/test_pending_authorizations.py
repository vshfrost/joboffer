"""Адаптер `PendingAuthorizations` у памʼяті: одноразове забирання й обмеження розміру."""

from datetime import UTC, datetime
from uuid import UUID

from domain.oauth.entities import CodeBinding, PendingAuthorization
from domain.oauth.ids import ClientId
from infrastructure.oauth.pending import InMemoryPendingAuthorizations

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def make(number: int = 1) -> PendingAuthorization:
    return PendingAuthorization(
        client_id=ClientId(UUID(int=number)),
        binding=CodeBinding(
            code_challenge=f"challenge-{number}",
            redirect_uri="https://claude.ai/api/mcp/auth_callback",
            redirect_uri_provided_explicitly=True,
        ),
        state=None,
        expires_at=NOW,
    )


def test_stored_request_is_returned_by_rid() -> None:
    pending = InMemoryPendingAuthorizations()
    pending.put("rid-1", make(1))

    assert pending.get("rid-1") == make(1)
    assert pending.get("rid-1") == make(1)


def test_unknown_rid_is_none() -> None:
    pending = InMemoryPendingAuthorizations()

    assert pending.get("nope") is None
    assert pending.take("nope") is None


def test_take_hands_the_request_out_once() -> None:
    pending = InMemoryPendingAuthorizations()
    pending.put("rid-1", make(1))

    assert pending.take("rid-1") == make(1)
    assert pending.take("rid-1") is None
    assert pending.get("rid-1") is None


def test_overflow_evicts_the_oldest_requests() -> None:
    pending = InMemoryPendingAuthorizations(max_size=2)
    for number in (1, 2, 3):
        pending.put(f"rid-{number}", make(number))

    assert pending.get("rid-1") is None
    assert pending.get("rid-2") == make(2)
    assert pending.get("rid-3") == make(3)
