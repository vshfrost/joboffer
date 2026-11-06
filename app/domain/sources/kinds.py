"""Види джерел: ATS-платформа компанії чи RSS-стрічка; з них складається `jobs.source`."""

from enum import StrEnum


class Platform(StrEnum):
    GREENHOUSE = "greenhouse"
    ASHBY = "ashby"
    LEVER = "lever"


class FeedSource(StrEnum):
    DOU = "dou"
    DJINNI = "djinni"


type SourceKind = Platform | FeedSource


def source_label(kind: SourceKind) -> str:
    """Значення `jobs.source`: `ats:<платформа>` або `rss:<джерело>`."""
    prefix = "ats" if isinstance(kind, Platform) else "rss"
    return f"{prefix}:{kind.value}"
