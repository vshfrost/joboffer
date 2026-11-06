"""Теми підготовки до інтерв'ю: Claude пропонує теми з прогалин проаналізованої вакансії, у базу
потрапляють лише погоджені користувачем. Тема спільна для всіх вакансій користувача (slug):
одна й та сама прогалина з кількох вакансій — одна тема з кількома прив'язками."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Self

from domain.prep.ids import TopicId
from domain.prep.plan import PrepStep, StepKind
from domain.shared.errors import InvalidValue
from domain.shared.text import one_line

MIN_SLUG_LENGTH = 2
MAX_SLUG_LENGTH = 60
MAX_TITLE_LENGTH = 120
MAX_SUMMARY_LENGTH = 1000
MAX_GAP_LENGTH = 300
MAX_TOPICS_PER_SAVE = 20
# Номери теми й кроку — INTEGER у базі: більший номер не може бути чиїмось.
MAX_NUMBER = 2**31 - 1
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class TopicKind(StrEnum):
    TECH = "tech"
    BEHAVIORAL = "behavioral"
    DOMAIN = "domain"


class TopicStatus(StrEnum):
    """Рахується з кроків плану; лише `ready` ставить користувач."""

    NEW = "new"
    PLANNED = "planned"
    LEARNING = "learning"
    PRACTICING = "practicing"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class NewTopic:
    """Тема, яку користувач погодив. Для наявної теми (той самий slug) поля замінюють старі."""

    slug: str
    title: str
    kind: TopicKind
    summary: str = ""
    deadline: date | None = None

    @classmethod
    def parse(
        cls, *, slug: str, title: str, kind: str, summary: str, deadline: str
    ) -> Self:
        slug = slug.strip()
        if not MIN_SLUG_LENGTH <= len(slug) <= MAX_SLUG_LENGTH or not SLUG.fullmatch(
            slug
        ):
            raise InvalidValue(
                "slug",
                f"slug {slug!r}: латиниця в нижньому регістрі, цифри й дефіси між словами, "
                f"{MIN_SLUG_LENGTH}–{MAX_SLUG_LENGTH} символів (напр. mysql-query-optimization).",
            )
        title = one_line(title)
        if not title or len(title) > MAX_TITLE_LENGTH:
            raise InvalidValue(
                "title", f"{slug}: назва — від 1 до {MAX_TITLE_LENGTH} символів."
            )
        try:
            topic_kind = TopicKind(kind.strip().lower())
        except ValueError:
            allowed = ", ".join(member.value for member in TopicKind)
            raise InvalidValue(
                "kind", f"{slug}: kind {kind!r} — допустимо {allowed}."
            ) from None
        summary = one_line(summary)
        if len(summary) > MAX_SUMMARY_LENGTH:
            raise InvalidValue(
                "summary", f"{slug}: опис — до {MAX_SUMMARY_LENGTH} символів."
            )
        return cls(slug, title, topic_kind, summary, _deadline(slug, deadline))


def parse_gap(slug: str, gap: str) -> str:
    """Яку прогалину вакансії закриває тема: обов'язково, один рядок."""
    gap = one_line(gap)
    if not gap or len(gap) > MAX_GAP_LENGTH:
        raise InvalidValue("gap", f"{slug}: gap — від 1 до {MAX_GAP_LENGTH} символів.")
    return gap


def check_unique_slugs(slugs: Iterable[str]) -> None:
    seen: set[str] = set()
    for slug in slugs:
        if slug in seen:
            raise InvalidValue("topics", f"Тема {slug} у списку двічі.")
        seen.add(slug)


@dataclass(frozen=True, slots=True)
class TopicJob:
    """Вакансія (за номером користувача), до якої прив'язана тема, і прогалина, яку тема закриває."""

    job_number: int
    title: str | None
    company: str | None
    score: int
    gap: str


@dataclass(frozen=True, slots=True)
class PrepTopic:
    """Збережена тема. `number` — номер у межах користувача, `id` — внутрішній ключ."""

    id: TopicId
    number: int
    slug: str
    title: str
    kind: TopicKind
    summary: str
    deadline: date | None
    created_at: datetime
    jobs: tuple[TopicJob, ...] = field(default=())
    # Кроки плану в порядку position; `ready_at` — коли користувач позначив тему готовою.
    steps: tuple[PrepStep, ...] = field(default=())
    ready_at: datetime | None = None

    @property
    def priority(self) -> int:
        """Чим більше вакансій потребують тему і чим вони кращі для користувача, тим вище."""
        return sum(job.score for job in self.jobs)

    @property
    def status(self) -> TopicStatus:
        if self.ready_at is not None:
            return TopicStatus.READY
        if not self.steps:
            return TopicStatus.NEW
        done = self.done
        if not done:
            return TopicStatus.PLANNED
        if any(step.kind is StepKind.PRACTICE for step in done):
            return TopicStatus.PRACTICING
        return TopicStatus.LEARNING

    @property
    def pending(self) -> tuple[PrepStep, ...]:
        return tuple(step for step in self.steps if step.done_at is None)

    @property
    def done(self) -> tuple[PrepStep, ...]:
        return tuple(step for step in self.steps if step.done_at is not None)

    @property
    def minutes_left(self) -> int:
        return sum(step.minutes for step in self.pending)

    @property
    def percent(self) -> int:
        """Готовність теми: позначена користувачем — 100, інакше частка виконаних кроків."""
        if self.ready_at is not None:
            return 100
        if not self.steps:
            return 0
        return _half_up(100 * len(self.done), len(self.steps))


def readiness(topics: Sequence[PrepTopic]) -> int | None:
    """Готовність до вакансії — середня готовність її тем; None — тем ще нема."""
    if not topics:
        return None
    return _half_up(sum(topic.percent for topic in topics), len(topics))


def _half_up(numerator: int, denominator: int) -> int:
    """Ціле ділення з округленням .5 вгору (round() округлює до парного: 8.5 → 8)."""
    return (2 * numerator + denominator) // (2 * denominator)


def by_priority(topics: Iterable[PrepTopic]) -> list[PrepTopic]:
    """Пріоритет спадає; за рівного — ближчий дедлайн, без дедлайну — нижче; далі старіші."""
    return sorted(
        topics,
        key=lambda topic: (
            -topic.priority,
            topic.deadline is None,
            topic.deadline or date.max,
            topic.number,
        ),
    )


def _deadline(slug: str, value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    try:
        if ISO_DATE.fullmatch(value):
            return date.fromisoformat(value)
    except ValueError:
        pass
    raise InvalidValue(
        "deadline", f"{slug}: deadline {value!r} — дата YYYY-MM-DD або порожньо."
    )
