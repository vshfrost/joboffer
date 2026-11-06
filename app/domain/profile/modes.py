"""Формат роботи й рівень посади: значення збігаються з MCP-контрактом v1."""

from collections.abc import Sequence
from enum import StrEnum


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class Seniority(StrEnum):
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"


def parse_members[Member: StrEnum](
    kind: type[Member], values: Sequence[str]
) -> frozenset[Member] | None:
    """Множина значень enum-а; невідоме значення — `None`."""
    try:
        return frozenset(kind(value) for value in values)
    except ValueError:
        return None
