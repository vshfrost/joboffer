"""Patch: «не передано» ≠ `None` («очистити») ≠ значення."""

from domain.shared.patch import UNSET, Patch, Unset


def apply(current: str | None, patch: Patch[str | None]) -> str | None:
    return current if isinstance(patch, Unset) else patch


def test_unset_is_distinct_from_none_and_values() -> None:
    assert UNSET is not None
    others: list[object] = [None, "", 0, False, "x"]
    assert all(other != UNSET for other in others)
    assert isinstance(UNSET, Unset)
    assert not isinstance(None, Unset)


def test_unset_keeps_none_clears_value_replaces() -> None:
    assert apply("старе", UNSET) == "старе"
    assert apply("старе", None) is None
    assert apply("старе", "нове") == "нове"
    assert apply(None, UNSET) is None


def test_unset_is_a_singleton() -> None:
    assert Unset.UNSET is UNSET
    assert len(Unset) == 1
