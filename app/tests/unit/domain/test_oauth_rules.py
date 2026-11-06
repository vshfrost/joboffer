"""Правила гранту: resource (scope перевіряє SDK)."""

import pytest

from domain.oauth.errors import InvalidTarget
from domain.oauth.rules import SCOPE, ensure_resource

RESOURCE = "https://agent.example/joboffer"


def test_missing_resource_is_bound_to_the_server_resource() -> None:
    assert ensure_resource(None, RESOURCE) == RESOURCE


def test_same_resource_is_accepted() -> None:
    assert ensure_resource(RESOURCE, RESOURCE) == RESOURCE


@pytest.mark.parametrize(
    "other",
    [
        "https://evil.example/joboffer",
        "https://agent.example/other",
        "https://agent.example/joboffer/",
        "",
    ],
)
def test_another_resource_is_rejected_as_invalid_target(other: str) -> None:
    with pytest.raises(InvalidTarget):
        ensure_resource(other, RESOURCE)


def test_scope_is_exactly_joboffer() -> None:
    assert SCOPE == "joboffer"
