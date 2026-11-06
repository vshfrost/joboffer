"""Результати підготовки для вебу: теми з відсотком готовності й лічильниками квізу. Кроки,
вакансії з прогалинами й статуси — ті самі `TopicData` / `TopicDetailData`, що в MCP; ключа оцінки
питань тут нема взагалі — лише скільки питань і скільки з них на повторенні."""

from dataclasses import dataclass

from application.contracts.prep import TopicData, TopicDetailData
from application.contracts.quiz import QuizCountData


@dataclass(frozen=True, slots=True, kw_only=True)
class TopicRowData:
    """Тема в реєстрі: готовність, %, питання квізу цієї теми."""

    topic: TopicData
    percent: int
    quiz: QuizCountData


@dataclass(frozen=True, slots=True, kw_only=True)
class TopicBoardData:
    """Теми за пріоритетом і загальні лічильники квізу по всіх темах."""

    topics: tuple[TopicRowData, ...]
    quiz: QuizCountData


@dataclass(frozen=True, slots=True, kw_only=True)
class TopicPageData:
    """Сторінка теми: кроки, вакансії з прогалинами, %, лічильники квізу."""

    detail: TopicDetailData
    percent: int
    quiz: QuizCountData


@dataclass(frozen=True, slots=True, kw_only=True)
class JobPrepData:
    """Підготовка до вакансії: її теми за пріоритетом і готовність (середнє по темах)."""

    readiness: int | None
    topics: tuple[TopicRowData, ...]
