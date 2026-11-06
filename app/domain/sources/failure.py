"""Чому джерело не віддало вакансії: код збою для стану прогону й аудиту (без вмісту)."""

from enum import StrEnum


class FailureReason(StrEnum):
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    # 5xx чи обрив з'єднання.
    UNAVAILABLE = "unavailable"
    # Інша відмова (4xx).
    REJECTED = "rejected"
    # Відповідь, яку не розібрати, не того вигляду чи завелика.
    INVALID = "invalid"
    # Для цього виду джерела нема адаптера.
    UNSUPPORTED = "unsupported"


class SourceError(Exception):
    """Джерело не віддало вакансії; `reason` потрапляє в аудит і стан прогону."""

    def __init__(self, reason: FailureReason) -> None:
        super().__init__(reason.value)
        self.reason = reason
