"""ID теми підготовки: внутрішній UUID запису. Назовні тема — завжди за номером у межах користувача."""

from dataclasses import dataclass
from typing import ClassVar

from domain.shared.ids import EntityId


@dataclass(frozen=True, slots=True)
class TopicId(EntityId):
    field_name: ClassVar[str] = "topic_id"


@dataclass(frozen=True, slots=True)
class StepId(EntityId):
    """ID кроку плану теми: внутрішній UUID запису. Назовні крок — за номером у межах користувача."""

    field_name: ClassVar[str] = "step_id"


@dataclass(frozen=True, slots=True)
class QuestionId(EntityId):
    """ID питання квізу: внутрішній UUID запису. Назовні питання — за номером у межах користувача."""

    field_name: ClassVar[str] = "question_id"


@dataclass(frozen=True, slots=True)
class AnswerId(EntityId):
    """ID відповіді в історії питання: внутрішній UUID запису."""

    field_name: ClassVar[str] = "answer_id"


@dataclass(frozen=True, slots=True)
class KitId(EntityId):
    """ID версії пакета до інтерв'ю: внутрішній UUID запису. Назовні версія — за номером у межах користувача."""

    field_name: ClassVar[str] = "kit_id"
