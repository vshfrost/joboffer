"""Команди й результати контексту prep: примітиви (значення будує use case)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from application.contracts.analysis import AnalysisData
from application.contracts.facts import FactData
from application.contracts.jobs import JobData
from domain.prep.plan import StepKind
from domain.prep.topic import TopicKind, TopicStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class TopicInput:
    """Сира тема з будь-якого транспорту; розбір і межі — у домені."""

    slug: str
    title: str
    kind: str
    gap: str
    summary: str = ""
    deadline: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class TopicJobData:
    """Вакансія, до якої прив'язана тема, і прогалина, яку тема закриває."""

    job_number: int
    title: str | None
    company: str | None
    score: int
    gap: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TopicData:
    """Тема з прив'язками. Статус і лічильники кроків рахуються з плану теми."""

    topic_number: int
    slug: str
    title: str
    kind: TopicKind
    summary: str
    deadline: date | None
    priority: int
    status: TopicStatus
    steps_done: int
    steps_total: int
    minutes_left: int
    jobs: tuple[TopicJobData, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class CvLineData:
    """Рядок останнього CV вакансії і факти, на яких він стоїть."""

    text: str
    facts: tuple[FactData, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class TopicsBriefData:
    """Усе, що потрібно Claude, щоб запропонувати теми під проаналізовану вакансію."""

    job: JobData
    analysis: AnalysisData
    topics: tuple[TopicData, ...]
    rules: str
    # Рядки останнього CV вакансії (порожньо, якщо CV нема): те, що треба вміти захистити.
    cv_lines: tuple[CvLineData, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceInput:
    title: str
    url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class StepInput:
    """Сирий крок плану з будь-якого транспорту; розбір і межі — у домені."""

    kind: str
    title: str
    minutes: int
    details: str = ""
    resources: Sequence[ResourceInput] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceData:
    title: str
    url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class StepData:
    """Крок плану. `done_at` — момент виконання (UTC); день за Мадридом показує транспорт."""

    step_number: int
    position: int
    kind: StepKind
    title: str
    minutes: int
    details: str
    resources: tuple[ResourceData, ...]
    done_at: datetime | None
    note: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TopicDetailData:
    """Тема з планом. `next_step_number` — перший невиконаний крок."""

    topic: TopicData
    next_step_number: int | None
    steps: tuple[StepData, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanBriefData:
    """Тема з вакансіями, прогалинами й поточним планом + правила плану для Claude."""

    detail: TopicDetailData
    rules: str
