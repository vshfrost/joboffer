"""Actor: незмінний, типізований, з інваріантами каналу, grant і scopes."""

import inspect
from dataclasses import FrozenInstanceError, fields
from typing import Any
from uuid import UUID

import pytest

from application.contracts.actor import Actor, Channel, Scope
from domain.identity.ids import GrantId, UserId
from domain.shared.errors import InvalidValue

USER = UserId(UUID(int=1))
GRANT = GrantId(UUID(int=2))


def make_actor(**overrides: Any) -> Actor:
    params: dict[str, Any] = {
        "user_id": USER,
        "channel": Channel.WEB,
        "client_id": "web",
        "grant_id": None,
        "scopes": frozenset({Scope.READ, Scope.WRITE}),
        "correlation_id": "req-1",
    }
    return Actor(**{**params, **overrides})


def test_web_actor_has_no_grant() -> None:
    actor = make_actor()
    assert (actor.user_id, actor.channel, actor.grant_id) == (USER, Channel.WEB, None)
    assert actor.scopes == {Scope.READ, Scope.WRITE}


def test_mcp_actor_requires_grant() -> None:
    assert make_actor(channel=Channel.MCP, grant_id=GRANT).grant_id == GRANT
    with pytest.raises(InvalidValue) as caught:
        make_actor(channel=Channel.MCP)
    assert caught.value.field == "grant_id"


@pytest.mark.parametrize("channel", [Channel.WEB, Channel.CLI])
def test_non_mcp_channels_forbid_grant(channel: Channel) -> None:
    with pytest.raises(InvalidValue) as caught:
        make_actor(channel=channel, grant_id=GRANT)
    assert caught.value.field == "grant_id"


@pytest.mark.parametrize("field", ["client_id", "correlation_id"])
@pytest.mark.parametrize("blank", ["", " ", "\t\n"])
def test_blank_client_and_correlation_are_rejected(field: str, blank: str) -> None:
    with pytest.raises(InvalidValue) as caught:
        make_actor(**{field: blank})
    assert caught.value.field == field


def test_client_id_is_opaque_and_kept_as_given() -> None:
    assert make_actor(client_id="Claude Desktop 1.2").client_id == "Claude Desktop 1.2"


def test_empty_scopes_are_rejected() -> None:
    with pytest.raises(InvalidValue) as caught:
        make_actor(scopes=frozenset())
    assert caught.value.field == "scopes"


def test_read_only_actor_is_valid() -> None:
    assert make_actor(scopes=frozenset({Scope.READ})).scopes == {Scope.READ}


def test_actor_is_immutable_and_hashable() -> None:
    actor = make_actor()
    with pytest.raises(FrozenInstanceError):
        actor.__setattr__("user_id", UserId(UUID(int=9)))
    assert actor == make_actor()
    assert hash(actor) == hash(make_actor())


def test_actor_fields_are_typed_values_not_a_request_body() -> None:
    assert {f.name for f in fields(Actor)} == {
        "user_id",
        "channel",
        "client_id",
        "grant_id",
        "scopes",
        "correlation_id",
    }
    assert Actor.__annotations__["user_id"] is UserId
    assert not [
        name
        for name, member in inspect.getmembers(Actor, callable)
        if not name.startswith("_")
    ]
