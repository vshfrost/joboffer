"""Відповідь користувача на прогалину аналізу: «є досвід» (з фактами) або «немає досвіду».

Відповідь прив'язана до тексту прогалини, а не до її номера: повторний аналіз із тією самою
прогалиною знову бачить відповідь, і агент не питає вдруге.
"""

from dataclasses import dataclass
from datetime import datetime

from domain.shared.errors import InvalidValue


@dataclass(frozen=True, slots=True)
class GapAnswer:
    gap: str
    has_experience: bool
    # Номери фактів користувача, що закривають прогалину; порожньо, коли досвіду нема.
    fact_numbers: tuple[int, ...]
    answered_at: datetime


def validate_answer(*, has_experience: bool, fact_count: int) -> None:
    """«Є досвід» вимагає хоч одного факту, «немає досвіду» — жодного. `InvalidValue` (поле
    `facts`) — відповідь суперечить собі."""
    if has_experience and fact_count == 0:
        raise InvalidValue(
            "facts",
            "Відповідь «є досвід» потребує хоча б одного факту — "
            "із формулюванням, яке користувач схвалив.",
        )
    if not has_experience and fact_count > 0:
        raise InvalidValue("facts", "Відповідь «немає досвіду» не може мати фактів.")
