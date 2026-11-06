"""Керування джерелами користувача: компанії ATS і RSS-стрічки, правила введення, помилки."""

import re
from dataclasses import dataclass, field

from domain.shared.errors import InvalidValue
from domain.sources.failure import FailureReason
from domain.sources.ids import SourceId
from domain.sources.kinds import FeedSource, Platform
from domain.sources.run import SourceRun

MAX_SLUG_LENGTH = 100
MAX_NAME_LENGTH = 200
# Слаг стає шляхом в URL ATS: лише безпечні символи.
SLUG_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# Параметр запиту стрічки: імʼя з необовʼязковим значенням (`remote`, `category=Python`);
# пробілів нема — рядок підставляється в URL як є.
QUERY_PARAM = r"[A-Za-z0-9_]{1,30}(?:=[A-Za-z0-9._+-]{1,50})?"
QUERY_PATTERN = re.compile(rf"{QUERY_PARAM}(?:&{QUERY_PARAM}){{0,5}}")
# Без цього параметра стрічка віддає все підряд.
REQUIRED_PARAM = {FeedSource.DOU: "category", FeedSource.DJINNI: "primary_keyword"}


@dataclass(frozen=True, slots=True)
class NewCompany:
    platform: Platform
    slug: str
    name: str


@dataclass(frozen=True, slots=True)
class NewFeed:
    source: FeedSource
    query: str


@dataclass(frozen=True, slots=True)
class Company:
    id: SourceId
    platform: Platform
    slug: str
    name: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class Feed:
    id: SourceId
    source: FeedSource
    query: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class CompanyRow:
    """Компанія й її останній прогін (`None` — прогону ще не було)."""

    company: Company
    run: SourceRun | None


@dataclass(frozen=True, slots=True)
class FeedRow:
    feed: Feed
    run: SourceRun | None


@dataclass(frozen=True, slots=True)
class SourceList:
    companies: list[CompanyRow] = field(default_factory=list)
    feeds: list[FeedRow] = field(default_factory=list)


def parse_company(platform: str, slug: str, name: str) -> NewCompany:
    """Платформа, слаг і назва з сирих значень форми; порожня назва — це слаг. `InvalidValue` —
    з полем (`platform` / `slug` / `name`)."""
    try:
        kind = Platform(platform.strip())
    except ValueError:
        raise InvalidValue("platform", "Невідома платформа.") from None
    slug = slug.strip()
    if len(slug) > MAX_SLUG_LENGTH or not SLUG_PATTERN.fullmatch(slug):
        raise InvalidValue(
            "slug", "Слаг компанії — літери, цифри, крапка, дефіс і підкреслення."
        )
    name = " ".join(name.split()) or slug
    if len(name) > MAX_NAME_LENGTH:
        raise InvalidValue(
            "name", f"Назва компанії — не довша за {MAX_NAME_LENGTH} символів."
        )
    return NewCompany(kind, slug, name)


def parse_feed(source: str, query: str) -> NewFeed:
    """Джерело й параметри стрічки з сирих значень форми. `InvalidValue` — з полем
    (`source` / `query`)."""
    try:
        kind = FeedSource(source.strip())
    except ValueError:
        raise InvalidValue("source", "Невідоме джерело стрічки.") from None
    query = query.strip()
    if not QUERY_PATTERN.fullmatch(query):
        raise InvalidValue(
            "query",
            "Параметри стрічки — name=value через &, без пробілів"
            " (напр. category=Python&remote).",
        )
    params = dict(param.partition("=")[::2] for param in query.split("&"))
    required = REQUIRED_PARAM[kind]
    if not params.get(required):
        raise InvalidValue(
            "query", f"Для стрічки {kind.value} потрібен параметр {required}=…"
        )
    return NewFeed(kind, query)


def company_exists() -> InvalidValue:
    return InvalidValue("slug", "Така компанія вже є в списку.")


def feed_exists() -> InvalidValue:
    return InvalidValue("query", "Така стрічка вже є в списку.")


def probe_failure(platform: Platform, slug: str, reason: FailureReason) -> InvalidValue:
    """Пробний запит не підтвердив слаг: компанії нема або перевірити не вдалось."""
    if reason is FailureReason.NOT_FOUND:
        return InvalidValue(
            "slug", f"Компанії зі слагом «{slug}» на {platform.value} не знайдено."
        )
    return InvalidValue(
        "slug", f"Не вдалося перевірити слаг ({reason.value}) — спробуй пізніше."
    )
