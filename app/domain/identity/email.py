"""Email користувача: нормалізований запис (нижній регістр, без пробілів).

Нормалізація явна й однакова для всіх доменів: Gmail-правила (крапки, `+tag`) не застосовуються.
"""

from dataclasses import dataclass
from typing import Self

from domain.shared.errors import InvalidValue

EMAIL_MAX = 254
LOCAL_MAX = 64

# Роздільники списку адрес у заголовку `To:`: `a,b@x.com` — це два отримувачі.
_HEADER_DELIMITERS = frozenset(',;:<>()[]"\\')
_NOT_NORMALIZED = "Email має бути нормалізований: нижній регістр, без пробілів на краях"
_MALFORMED = "Email має вигляд імʼя@домен.зона, без пробілів"


def _well_formed(value: str) -> bool:
    local, at, domain = value.partition("@")
    return (
        bool(at)
        and 0 < len(local) <= LOCAL_MAX
        and len(value) <= EMAIL_MAX
        and "@" not in domain
        and "." in domain
        and not domain.startswith(".")
        and not domain.endswith(".")
        and ".." not in domain
        and value.isprintable()
        and not any(char.isspace() for char in value)
        and _HEADER_DELIMITERS.isdisjoint(value)
    )


@dataclass(frozen=True, slots=True)
class Email:
    """Конструктор лише перевіряє; `parse` спершу нормалізує сирий ввід."""

    value: str

    def __post_init__(self) -> None:
        if self.value != self.value.strip().lower():
            raise InvalidValue("email", _NOT_NORMALIZED)
        if not _well_formed(self.value):
            raise InvalidValue("email", _MALFORMED)

    @classmethod
    def parse(cls, raw: str) -> Self:
        return cls(raw.strip().lower())
