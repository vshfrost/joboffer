"""Typed ID: лише канонічний UUID, незмінність, різні типи не рівні."""

from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from domain.identity.ids import GrantId, UserId
from domain.shared.errors import InvalidValue
from domain.shared.ids import EntityId

# Нові typed ID контекстів додавай сюди: на них діють ті самі правила.
ALL_IDS: list[type[EntityId]] = [UserId, GrantId]
FIELD_NAMES = {UserId: "user_id", GrantId: "grant_id"}
VALID = "12345678-1234-4234-8234-123456789abc"

real_uuids = st.uuids().filter(lambda u: u.int != 0)


def _assign(obj: object, name: str, value: object) -> None:
    setattr(obj, name, value)


@pytest.mark.parametrize("id_type", ALL_IDS)
@pytest.mark.parametrize(
    "raw",
    [
        "",
        " ",
        "not-a-uuid",
        VALID.upper(),
        f"{{{VALID}}}",
        f"urn:uuid:{VALID}",
        VALID.replace("-", ""),
        f" {VALID}",
        f"{VALID}\n",
        "00000000-0000-0000-0000-000000000000",
        VALID[:-1],
        VALID + "0",
        "١٢٣٤٥٦٧٨-١٢٣٤-٤٢٣٤-٨٢٣٤-١٢٣٤٥٦٧٨٩abc",
    ],
)
def test_parse_rejects_non_canonical_and_nil(id_type: type[EntityId], raw: str) -> None:
    with pytest.raises(InvalidValue) as caught:
        id_type.parse(raw)
    assert caught.value.field == FIELD_NAMES[id_type]
    assert caught.value.code == "invalid_value"


@pytest.mark.parametrize("id_type", ALL_IDS)
def test_constructor_rejects_nil(id_type: type[EntityId]) -> None:
    with pytest.raises(InvalidValue):
        id_type(UUID(int=0))


@pytest.mark.parametrize("id_type", ALL_IDS)
@given(value=real_uuids)
def test_roundtrip_str_to_id_to_str(id_type: type[EntityId], value: UUID) -> None:
    parsed = id_type.parse(str(value))
    assert str(parsed) == str(value)
    assert parsed == id_type(value)


@pytest.mark.parametrize("id_type", ALL_IDS)
@given(raw=st.text())
def test_parse_accepts_only_what_it_prints_back(
    id_type: type[EntityId], raw: str
) -> None:
    try:
        parsed = id_type.parse(raw)
    except InvalidValue:
        return
    assert str(parsed) == raw


@given(value=real_uuids)
def test_same_uuid_in_different_id_types_is_not_equal(value: UUID) -> None:
    ids = [id_type(value) for id_type in ALL_IDS]
    for i, left in enumerate(ids):
        assert left == id_type_of(left)(value)
        for right in ids[i + 1 :]:
            assert left != right
        assert left != value


def id_type_of(identifier: EntityId) -> type[EntityId]:
    return type(identifier)


@pytest.mark.parametrize("id_type", ALL_IDS)
def test_id_is_immutable_and_hashable(id_type: type[EntityId]) -> None:
    identifier = id_type(UUID(VALID))
    with pytest.raises(FrozenInstanceError):
        _assign(identifier, "value", UUID(int=1))
    with pytest.raises(FrozenInstanceError):
        _assign(identifier, "extra", 1)
    assert {identifier: 1}[id_type(UUID(VALID))] == 1
