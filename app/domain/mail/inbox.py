"""«Вхідні» користувача: сторінки й фільтри списку листів, відкинуті листи в ньому, ліміт синку
вручну. Текст, відправник і тема листа — недовірені дані третіх сторін."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from domain.mail.mail import DropReason, MailCategory
from domain.mail.sender_auth import SenderAuth
from domain.shared.errors import DomainError
from domain.shared.local_time import local_time
from domain.shared.problems import Problems
from domain.shared.text import is_invisible

# Скільки останніх листів показує get_mail_inbox і «Вхідні» за замовчуванням.
RECENT_MAIL_LIMIT = 20
# Дозволені розміри сторінки списку листів.
MAIL_PAGE_SIZES = (20, 50, 100)
# За скільки останніх днів «Вхідні» і get_mail_inbox показують відкинуті листи.
DROPPED_NOTICE_WINDOW = timedelta(days=30)
# Синк вручну: не більше стількох запитів користувача за ковзне вікно.
MANUAL_SYNC_LIMIT = 2
MANUAL_SYNC_WINDOW = timedelta(minutes=30)
# Найдовший пошуковий запит.
MAX_QUERY = 200
# Скільки тексту листа показує читалка: відповідь із підписом уміщається.
DISPLAY_TEXT_LIMIT = 8000
# Посилання в тексті листа: показуються текстом, хост — у ASCII (punycode).
URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
# Два й більше порожніх рядки підряд.
BLANK_LINES = re.compile(r"\n(?:[ \t]*\n){2,}")
# Хост посилання: усе між «://» і першим «/», «?» чи «#» (розбір без urllib — його в домені заборонено).
_NETLOC = re.compile(r"https?://(?P<netloc>[^/?#]*)", re.IGNORECASE)


class MailError(DomainError):
    """Пошта недоступна користувачу; повідомлення показується як є."""

    code = "mail_error"


class MailNotConfigured(MailError):
    """Нема адреси скриньки застосунку: пошта не налаштована."""

    code = "mail_not_configured"

    def __init__(self) -> None:
        super().__init__("Пошту не налаштовано: нема адреси скриньки застосунку.")


class ManualSyncLimit(MailError):
    """Ліміт синку вручну вичерпано; next_at — коли звільниться наступний запит."""

    code = "manual_sync_limit"
    next_at: datetime

    def __init__(self, next_at: datetime) -> None:
        super().__init__(
            f"Синк уже запитано {MANUAL_SYNC_LIMIT} рази за 30 хв — "
            f"наступний о {local_time(next_at):%H:%M} (Мадрид)."
        )
        self.next_at = next_at


class MailKind(StrEnum):
    """Вид листа у фільтрі «Вхідних»: група категорій або відкинуті листи."""

    COMPANY = "company"
    LINKEDIN_ALERT = "linkedin_alert"
    LINKEDIN_MESSAGE = "linkedin_message"
    FORWARDING_CONFIRMATION = "forwarding_confirmation"
    OTHER = "other"
    DROPPED = "dropped"

    @property
    def categories(self) -> frozenset[MailCategory]:
        """Категорії збережених листів цього виду; для відкинутих — порожньо."""
        return _KIND_CATEGORIES[self]


_KIND_CATEGORIES: dict[MailKind, frozenset[MailCategory]] = {
    MailKind.COMPANY: frozenset({MailCategory.COMPANY}),
    MailKind.LINKEDIN_ALERT: frozenset({MailCategory.LINKEDIN_ALERT}),
    MailKind.LINKEDIN_MESSAGE: frozenset(
        {MailCategory.LINKEDIN_MESSAGE, MailCategory.LINKEDIN_APPLICATION}
    ),
    MailKind.FORWARDING_CONFIRMATION: frozenset({MailCategory.FORWARDING_CONFIRMATION}),
    # Підозрілі листи тут: окремого виду для підробок у фільтрі нема, а позначку видно в рядку.
    MailKind.OTHER: frozenset({MailCategory.OTHER, MailCategory.SUSPICIOUS}),
    MailKind.DROPPED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class MailPage:
    """Сторінка списку: номер з 1, розмір і скільки листів усього. Сторінка за межею списку —
    порожня (`in_range` False), не помилка."""

    number: int
    size: int
    total: int = 0

    @property
    def offset(self) -> int:
        return (self.number - 1) * self.size

    @property
    def in_range(self) -> bool:
        return self.offset < self.total

    @property
    def first(self) -> int:
        """Номер першого листа сторінки у списку (з 1)."""
        return self.offset + 1

    @property
    def last(self) -> int:
        return min(self.offset + self.size, self.total)

    @property
    def has_newer(self) -> bool:
        return self.number > 1

    @property
    def has_older(self) -> bool:
        return self.offset + self.size < self.total


FIRST_MAIL_PAGE = MailPage(1, RECENT_MAIL_LIMIT)


@dataclass(frozen=True, slots=True)
class MailQuery:
    """Що шукають у «Вхідних»: підрядок (відправник, тема, текст), вид, сторінка."""

    text: str = ""
    kind: MailKind | None = None
    page: MailPage = FIRST_MAIL_PAGE

    @classmethod
    def parse(
        cls,
        *,
        text: str = "",
        kind: str = "",
        page: int = 1,
        per_page: int = RECENT_MAIL_LIMIT,
    ) -> MailQuery:
        """`InvalidFields` — усі помилки полів разом (kind, page, per_page, q)."""
        problems = Problems()
        cleaned = text.strip()
        if len(cleaned) > MAX_QUERY:
            problems.add("q", f"Пошуковий запит — не довше {MAX_QUERY} символів.")
        parsed_kind = None
        if kind.strip():
            try:
                parsed_kind = MailKind(kind.strip())
            except ValueError:
                allowed = ", ".join(item.value for item in MailKind)
                problems.add("kind", f"Вид — один з: {allowed}.")
        if page < 1:
            problems.add("page", "Сторінка — від 1.")
        if per_page not in MAIL_PAGE_SIZES:
            allowed = ", ".join(map(str, MAIL_PAGE_SIZES))
            problems.add("per_page", f"per_page — один з: {allowed}.")
        problems.raise_if_any()
        return cls(cleaned, parsed_kind, MailPage(page, per_page))


@dataclass(frozen=True, slots=True)
class MailSummary:
    """Збережений лист без тексту. Відправник, ім'я й тема — недовірені дані."""

    id: int
    from_address: str
    from_name: str
    subject: str
    category: MailCategory
    received_at: datetime
    sender_auth: SenderAuth = SenderAuth.UNKNOWN


@dataclass(frozen=True, slots=True)
class StoredMail:
    """Лист із текстом (недовіреним, як у базі)."""

    summary: MailSummary
    text: str


@dataclass(frozen=True, slots=True)
class MailListItem:
    """Рядок «Вхідних»: збережений лист або відкинутий (з причиною, без тексту й вердикту)."""

    id: int
    dropped: bool
    from_address: str
    from_name: str
    subject: str
    received_at: datetime
    category: MailCategory | None = None
    sender_auth: SenderAuth | None = None
    reason: DropReason | None = None


@dataclass(frozen=True, slots=True)
class MailList:
    items: tuple[MailListItem, ...]
    page: MailPage


@dataclass(frozen=True, slots=True)
class DroppedSummary:
    """Відкинуті листи користувача за вікно: скільки й коли надійшов останній."""

    count: int = 0
    last_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ManualSync:
    """Синк вручну для користувача: скільки запитів лишилось у вікні й коли звільниться
    наступний (None — запити є)."""

    remaining: int
    next_at: datetime | None = None


def manual_sync(requested: Sequence[datetime], now: datetime) -> ManualSync:
    """Ліміт MANUAL_SYNC_LIMIT запитів за ковзне вікно MANUAL_SYNC_WINDOW: запит старший
    за вікно вже не рахується."""
    recent = sorted(at for at in requested if at > now - MANUAL_SYNC_WINDOW)
    if len(recent) < MANUAL_SYNC_LIMIT:
        return ManualSync(MANUAL_SYNC_LIMIT - len(recent))
    return ManualSync(0, recent[len(recent) - MANUAL_SYNC_LIMIT] + MANUAL_SYNC_WINDOW)


def display_text(text: str) -> str:
    """Текст листа для людини. Лист — недовірені дані, тож: без невидимих символів (bidi
    перевертає порядок, zero-width ховає слова), хост посилання — у punycode (`xn--…` замість
    літер-двійників, як кирилична «а» в «pаypal.com»), порожні рядки підряд — один, не довше
    за DISPLAY_TEXT_LIMIT. Клікабельними посилання не стають: шаблон показує лише текст."""
    clean = "".join(c for c in text.replace("\r\n", "\n") if not is_invisible(c))
    clean = BLANK_LINES.sub("\n\n", URL.sub(_ascii_host, clean)).strip()
    if len(clean) <= DISPLAY_TEXT_LIMIT:
        return clean
    shown = clean[:DISPLAY_TEXT_LIMIT].rstrip()
    return f"{shown}\n… (показано перші {DISPLAY_TEXT_LIMIT} символів)"


def _ascii_host(found: re.Match[str]) -> str:
    url = found.group(0)
    netloc = _NETLOC.match(url).group("netloc")  # type: ignore[union-attr]
    if ("[" in netloc) != (
        "]" in netloc
    ):  # зламаний IPv6 у [] — коди не-ASCII символів
        return _escaped(url)
    if netloc.isascii():
        return url
    userinfo, at, hostport = netloc.rpartition("@")
    host, colon, port = hostport.partition(":")
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:  # не IDNA-ім'я: коди символів одразу видають підробку
        ascii_host = _escaped(host)
    return url.replace(netloc, f"{userinfo}{at}{ascii_host}{colon}{port}", 1)


def _escaped(text: str) -> str:
    return text.encode("ascii", "backslashreplace").decode("ascii")
