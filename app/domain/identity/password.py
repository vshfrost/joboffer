"""Хеш пароля: непрозорий рядок від адаптера хешування.

Сирого пароля домен не бачить. Хеш не показується в repr, щоб не потрапити в логи й тексти помилок.
"""

from dataclasses import dataclass, field

from domain.shared.errors import InvalidValue


@dataclass(frozen=True, slots=True)
class PasswordHash:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.value:
            raise InvalidValue("password_hash", "Хеш пароля не може бути порожнім")
