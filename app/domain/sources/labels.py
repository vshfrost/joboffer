"""Формат роботи за позначкою ATS."""

from domain.profile.modes import WorkMode


def parse_work_mode_label(label: str | None) -> WorkMode | None:
    """«Remote», «Hybrid», «OnSite» / «on-site» → формат; «Unspecified» і решта — None."""
    key = (label or "").strip().casefold().replace("-", "").replace("_", "")
    return {
        "remote": WorkMode.REMOTE,
        "hybrid": WorkMode.HYBRID,
        "onsite": WorkMode.ONSITE,
    }.get(key)
