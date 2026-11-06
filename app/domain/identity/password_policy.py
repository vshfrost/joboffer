"""Політика пароля для реєстрації: від 8 символів і цифра, мала й велика літера, спецсимвол."""

from domain.identity.errors import PasswordWeak
from domain.shared.errors import InvalidValue

PASSWORD_MIN = 8
PASSWORD_MAX = 1024


def _special(char: str) -> bool:
    # Будь-що, що не буква, не цифра й не пробільне: підкреслення, дефіс, знаки, емодзі.
    return not char.isalnum() and not char.isspace()


def check_new_password(raw: str) -> None:
    """Довжина поза межами — `InvalidValue`; бракує класу символів — `PasswordWeak`."""
    if not PASSWORD_MIN <= len(raw) <= PASSWORD_MAX:
        raise InvalidValue(
            "password", f"Пароль — від {PASSWORD_MIN} до {PASSWORD_MAX} символів"
        )
    missing = [
        name
        for name, present in (
            ("цифру", any(char.isdigit() for char in raw)),
            ("малу літеру", any(char.islower() for char in raw)),
            ("велику літеру", any(char.isupper() for char in raw)),
            ("спецсимвол", any(_special(char) for char in raw)),
        )
        if not present
    ]
    if missing:
        raise PasswordWeak(f"Додай до пароля: {', '.join(missing)}")
