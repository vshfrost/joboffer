"""Фільтр вакансій за профілем: чому вакансію з джерела не беремо.

Усе береться з профілю: слова назви (`title_keywords` / `title_exclude`, у т.ч. рівні на кшталт
junior), загальні формати, місця зі синонімами й форматами. Порожнє поле профілю — обмеження нема.
`stop_words` лише знижують пріоритет при аналізі, тут їх нема."""

from collections.abc import Iterable
from enum import StrEnum

from domain.jobs.job import Job
from domain.profile.locations import SearchLocation
from domain.profile.modes import WorkMode
from domain.profile.profile import Profile
from domain.sources.fold import fold, has_phrase, has_stem, has_term
from domain.sources.posting import Posting

# Основи слів (порівнюються після `fold`): формат вакансії в тексті.
REMOTE_STEMS = ("remote", "віддален", "дистанційн", "удален", "удалён")
HYBRID_STEMS = ("hybrid", "гібрид", "гибрид")
FEED_SOURCE_PREFIX = "rss:"


class Skip(StrEnum):
    """Чому вакансію з джерела не взято."""

    EMPTY = "empty"
    TITLE = "title"
    EXCLUDED = "excluded"
    FORMAT = "format"
    LOCATION = "location"


def infer_mode(texts: Iterable[str]) -> WorkMode | None:
    """Формат за словами в тексті (EN / UK / RU): hybrid сильніший за remote («гібрид, іноді
    віддалено»). Нічого не сказано — None."""
    folded = " ".join(fold(text) for text in texts)
    if any(has_stem(folded, stem) for stem in HYBRID_STEMS):
        return WorkMode.HYBRID
    if any(has_stem(folded, stem) for stem in REMOTE_STEMS):
        return WorkMode.REMOTE
    return None


def skip_reason(posting: Posting, profile: Profile) -> Skip | None:
    """Чому вакансію не беремо за профілем, або None. Порядок: порожній текст, назва, формат, локація."""
    if not posting.text:
        return Skip.EMPTY
    return (
        _title_skip(posting, profile)
        or _format_skip(posting, profile)
        or _location_skip(posting, profile)
    )


def stored_skip_reason(job: Job, profile: Profile) -> Skip | None:
    """Те саме для вакансії, що вже збережена: `Posting` збирається з її полів (локація — `jobs.location`,
    формат — зі слів у локації й тексті; невідомий — `include_unknown_mode`). Стрічка RSS шукає місце ще
    й у назві й тексті (структурованої локації там нема й не було). Вакансія ATS без локації — лише
    правила назви: локацію й формат судити нема з чого."""
    from_feed = job.source.startswith(FEED_SOURCE_PREFIX)
    posting = Posting(
        title=job.title or "",
        url=job.url or "",
        text=job.text or "",
        company=job.company,
        locations=(job.location,) if job.location else (),
        work_mode=infer_mode([job.location or "", job.text or ""]),
        locations_in_text=from_feed,
    )
    if job.location is None and not from_feed:
        return _title_skip(posting, profile)
    return skip_reason(posting, profile)


def _title_skip(posting: Posting, profile: Profile) -> Skip | None:
    title = fold(posting.title)
    rules = profile.rules
    keywords = [fold(word) for word in rules.title_keywords]
    if keywords and not any(has_phrase(title, word) for word in keywords):
        return Skip.TITLE
    excluded = (fold(word) for word in rules.title_exclude)
    return Skip.EXCLUDED if any(has_phrase(title, word) for word in excluded) else None


def _format_skip(posting: Posting, profile: Profile) -> Skip | None:
    modes = profile.locations.work_modes
    mode = _mode(posting)
    return Skip.FORMAT if modes and mode and mode not in modes else None


def _mode(posting: Posting) -> WorkMode | None:
    # Greenhouse не віддає формат окремо: «Remote - Spain», «Madrid (Remote)».
    return posting.work_mode or infer_mode(posting.locations)


def _location_skip(posting: Posting, profile: Profile) -> Skip | None:
    """Локація проходить, якщо містить місце чи синонім з профілю і формат вакансії — серед
    форматів цього місця. Формат невідомий: `include_unknown_mode`. Локація — структуровані поля
    джерела; стрічки без них шукають ще й у назві й тексті."""
    places = profile.locations.locations
    if not places:
        return None
    texts = [*posting.locations, *posting.countries]
    if posting.locations_in_text:
        texts += [posting.title, posting.text]
    folded = [fold(text) for text in texts]
    mode = _mode(posting)
    unknown_ok = profile.locations.include_unknown_mode
    for place in places:
        if _mentions(folded, place) and (
            unknown_ok if mode is None else mode in place.work_modes
        ):
            return None
    return Skip.LOCATION


def _mentions(folded: list[str], place: SearchLocation) -> bool:
    return any(
        has_term(text, term)
        for term in (place.place, *place.aliases)
        for text in folded
    )
