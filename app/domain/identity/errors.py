"""Помилки контексту identity: стабільний код, повідомлення українською, без HTTP."""

from typing import ClassVar

from domain.shared.errors import Conflict, DomainError, InvalidValue, NotFound

# Одне повідомлення на всі причини невдалого входу: відповідь не розкриває, чи є такий email.
INVALID_CREDENTIALS_MESSAGE = "Невірний email або пароль"
NOT_AUTHENTICATED_MESSAGE = "Потрібен вхід"


class InvalidCredentials(DomainError):
    """Email або пароль не підійшли. HTTP 401 дає транспорт входу, не домен."""

    code: ClassVar[str] = "invalid_credentials"


class EmailTaken(Conflict):
    """Користувач із таким (нормалізованим) email уже існує."""

    code: ClassVar[str] = "email_taken"


class NotAuthenticated(DomainError):
    """Сесії нема, вона невідома, прострочена або вже закрита. HTTP 401 дає транспорт."""

    code: ClassVar[str] = "not_authenticated"


class TooManyAttempts(DomainError):
    """Забагато невдалих входів: до `retry_after` секунд нові спроби не приймаються."""

    code: ClassVar[str] = "too_many_attempts"

    def __init__(self, message: str, *, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class EmailRequired(DomainError):
    """Провайдер не передав підтверджений email: вхід через нього неможливий."""

    code: ClassVar[str] = "email_required"


class AltchaFailed(DomainError):
    """Розв'язок proof-of-work не прийнято: підпис, строк, число, payload чи повторне використання. HTTP 422."""

    code: ClassVar[str] = "challenge_failed"


class RegistrationClosed(DomainError):
    """Ключ підпису altcha не налаштовано: реєстрація закрита. HTTP 503 дає транспорт."""

    code: ClassVar[str] = "registration_closed"


class InviteInvalid(NotFound):
    """Запрошення невідоме, прострочене або вже використане: причини не розрізняються."""

    code: ClassVar[str] = "invite_invalid"


class SignupClosed(NotFound):
    """Реєстрація закрита (`JOBOFFER_SIGNUP_MODE=closed`)."""

    code: ClassVar[str] = "signup_closed"


class PasswordWeak(InvalidValue):
    """Пароль не має цифри, малої, великої літери чи спецсимволу. HTTP 422."""

    code = "password_weak"

    def __init__(self, message: str) -> None:
        super().__init__("password", message)


class SignupExpired(InvalidValue):
    """Запит на реєстрацію невідомий, прострочений або вичерпав спроби коду. HTTP 422."""

    code = "signup_expired"

    def __init__(self, message: str) -> None:
        super().__init__("signup_id", message)


class CodeIncorrect(InvalidValue):
    """Код із листа не підійшов; `attempts_left` — скільки спроб ще лишилось. HTTP 422."""

    code = "code_incorrect"

    def __init__(self, message: str, *, attempts_left: int) -> None:
        super().__init__("code", message)
        self.attempts_left = attempts_left


class InviteAlreadyUsed(Conflict):
    """Запрошення погасили, поки очікували код: користувача не створено. HTTP 409."""

    code: ClassVar[str] = "invite_used"


class SignupMailUnavailable(DomainError):
    """Лист не вдалося відправити (збій пошти чи вичерпано добовий ліміт). HTTP 503."""

    code: ClassVar[str] = "mail_unavailable"
