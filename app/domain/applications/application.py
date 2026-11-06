"""Подача на вакансію: коли, яким каналом і куди користувач подався і де він у воронці.

Статус рухається лише вперед: applied → replied → interview → offer; rejected і withdrawn
закривають подачу. Домени й адреси компанії потрібні, щоб зіставляти її листи з подачею.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Self, cast

from domain.shared.errors import InvalidValue
from domain.shared.problems import Problems

MAX_CONTACTS = 10
ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
DOMAIN = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
EMAIL = re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?P<domain>[^@\s]+)")
# Хост посилання: без схеми, `user:pass@` і порту (розбір без urllib — його в домені заборонено).
URL_HOST = re.compile(r"[a-z][a-z0-9+.-]*://(?:[^/?#@]*@)?(?P<host>[^/?#:]*)")


class ApplicationStatus(StrEnum):
    APPLIED = "applied"
    REPLIED = "replied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ApplicationChannel(StrEnum):
    EMAIL = "email"
    ATS = "ats"
    LINKEDIN = "linkedin"
    REFERRAL = "referral"


class AtsPlatform(StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKABLE = "workable"
    SMARTRECRUITERS = "smartrecruiters"
    OTHER = "other"


Status = ApplicationStatus
# Куди можна перейти з кожного статусу: лише вперед (з пропусками); закриті — нікуди.
TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    Status.APPLIED: frozenset(
        {
            Status.REPLIED,
            Status.INTERVIEW,
            Status.OFFER,
            Status.REJECTED,
            Status.WITHDRAWN,
        }
    ),
    Status.REPLIED: frozenset(
        {Status.INTERVIEW, Status.OFFER, Status.REJECTED, Status.WITHDRAWN}
    ),
    Status.INTERVIEW: frozenset({Status.OFFER, Status.REJECTED, Status.WITHDRAWN}),
    Status.OFFER: frozenset({Status.WITHDRAWN}),
    Status.REJECTED: frozenset(),
    Status.WITHDRAWN: frozenset(),
}
# Групи для списку: відкриті подачі й закриті (rejected, withdrawn).
ACTIVE_STATUSES = frozenset(
    {Status.APPLIED, Status.REPLIED, Status.INTERVIEW, Status.OFFER}
)
CLOSED_STATUSES = frozenset({Status.REJECTED, Status.WITHDRAWN})
STATUS_GROUPS = {"active": ACTIVE_STATUSES, "closed": CLOSED_STATUSES}


@dataclass(frozen=True, slots=True)
class CvVersion:
    """Версія CV, з якою подались: номер документа, день збереження (за Мадридом) і сире
    покриття слів вакансії; None — вакансію на той момент не було проаналізовано. Самого файлу
    подача не тримає: у вакансії лишається лише останнє CV."""

    number: int
    saved_on: date
    coverage_percent: int | None


@dataclass(frozen=True, slots=True)
class NewApplication:
    """Деталі подачі; статус до них не належить — його змінюють лише переходи."""

    applied_on: date
    channel: ApplicationChannel
    ats: AtsPlatform | None = None
    company_domains: tuple[str, ...] = ()
    company_emails: tuple[str, ...] = ()
    # CV, яке було актуальним у момент подачі; None — CV під вакансію ще не було.
    cv: CvVersion | None = None

    @classmethod
    def parse(  # noqa: PLR0913 — по параметру на поле форми
        cls,
        *,
        applied_on: str,
        today: date,
        channel: str,
        ats: str,
        company_domains: Sequence[str],
        company_emails: Sequence[str],
    ) -> Self:
        """`InvalidFields` — усі помилки полів разом (тексти v1)."""
        problems = Problems()
        day = _parse_applied_on(applied_on, today, problems)
        parsed_channel = _parse_enum(
            ApplicationChannel, channel, "channel", "Канал", problems
        )
        parsed_ats = (
            _parse_enum(AtsPlatform, ats, "ats", "ATS", problems)
            if ats.strip()
            else None
        )
        domains = _contacts(
            "company_domains", company_domains, _parse_domain, "доменів", problems
        )
        emails = _contacts(
            "company_emails", company_emails, _parse_email, "адрес", problems
        )
        problems.raise_if_any()
        return cls(
            applied_on=cast("date", day),
            channel=cast("ApplicationChannel", parsed_channel),
            ats=parsed_ats,
            company_domains=domains,
            company_emails=emails,
        )


@dataclass(frozen=True, slots=True)
class Application:
    job_number: int
    status: ApplicationStatus
    applied_on: date
    channel: ApplicationChannel
    ats: AtsPlatform | None
    company_domains: tuple[str, ...]
    company_emails: tuple[str, ...]
    status_changed_at: datetime
    # None — «невідомо»: подачу зроблено без CV чи до того, як подача почала його пам'ятати.
    cv: CvVersion | None = None


def parse_status(value: str) -> ApplicationStatus:
    """`InvalidValue` (поле `status`) — невідомий статус."""
    problems = Problems()
    parsed = _parse_enum(ApplicationStatus, value, "status", "Статус", problems)
    problems.raise_if_any()
    return cast("ApplicationStatus", parsed)


def parse_status_filter(value: str) -> frozenset[ApplicationStatus]:
    """Статус або група: `active` (applied … offer) чи `closed` (rejected, withdrawn)."""
    cleaned = value.strip()
    if cleaned in STATUS_GROUPS:
        return STATUS_GROUPS[cleaned]
    try:
        return frozenset({ApplicationStatus(cleaned)})
    except ValueError as exc:
        allowed = ", ".join([*(s.value for s in ApplicationStatus), *STATUS_GROUPS])
        raise InvalidValue("status", f"Статус — один з: {allowed}.") from exc


def allowed_transitions(status: ApplicationStatus) -> tuple[ApplicationStatus, ...]:
    """Куди подачу можна рухати зараз, у порядку воронки."""
    return tuple(s for s in ApplicationStatus if s in TRANSITIONS[status])


def check_transition(current: ApplicationStatus, new: ApplicationStatus) -> bool:
    """True — статус зміниться; False — той самий, нічого робити. Перехід назад чи з
    закритої подачі — `InvalidValue` з причиною."""
    if new == current:
        return False
    if new in TRANSITIONS[current]:
        return True
    if not TRANSITIONS[current]:
        raise InvalidValue(
            "status",
            f"Подачу вже закрито ({current.value}): статус більше не змінюється.",
        )
    raise InvalidValue(
        "status",
        f"Статус {current.value} → {new.value} неможливий: він рухається лише вперед "
        "(applied → replied → interview → offer; rejected і withdrawn закривають подачу).",
    )


def _parse_applied_on(value: str, today: date, problems: Problems) -> date | None:
    """Дата подачі: порожньо — сьогодні; майбутня — помилка."""
    cleaned = value.strip()
    if not cleaned:
        return today
    parsed: date | None = None
    if ISO_DATE.fullmatch(cleaned):
        try:
            parsed = date.fromisoformat(cleaned)
        except ValueError:
            parsed = None
    if parsed is None:
        problems.add("applied_on", "Дата подачі — у форматі YYYY-MM-DD.")
        return None
    if parsed > today:
        problems.add("applied_on", "Дата подачі не може бути в майбутньому.")
        return None
    return parsed


def _parse_enum[E: StrEnum](
    enum: type[E], value: str, field: str, name: str, problems: Problems
) -> E | None:
    try:
        return enum(value.strip())
    except ValueError:
        allowed = ", ".join(item.value for item in enum)
        problems.add(field, f"{name} — один з: {allowed}.")
        return None


def _contacts(
    field: str,
    values: Sequence[str],
    parse: Callable[[str], str],
    name: str,
    problems: Problems,
) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if not value.strip():
            continue
        try:
            parsed = parse(value)
        except InvalidValue as error:
            problems.add(field, error.message)
            return ()
        if parsed not in result:
            result.append(parsed)
    if len(result) > MAX_CONTACTS:
        problems.add(field, f"Не більше {MAX_CONTACTS} {name} компанії.")
    return tuple(result)


def _parse_domain(value: str) -> str:
    """Домен пошти компанії: нижній регістр, без схеми, шляху, «www.» і «@» спереду."""
    cleaned = value.strip().lower()
    if "://" in cleaned:
        found = URL_HOST.match(cleaned)
        cleaned = found.group("host") if found else ""
    cleaned = cleaned.removeprefix("@").removeprefix("www.").rstrip(".")
    if not DOMAIN.fullmatch(cleaned):
        raise InvalidValue(
            "company_domains", f"Некоректний домен компанії: {value.strip()}."
        )
    return cleaned


def _parse_email(value: str) -> str:
    cleaned = value.strip().lower()
    found = EMAIL.fullmatch(cleaned)
    if found is None or not DOMAIN.fullmatch(found.group("domain")):
        raise InvalidValue(
            "company_emails", f"Некоректна адреса компанії: {value.strip()}."
        )
    return cleaned
