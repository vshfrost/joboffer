"""Приховування вакансій («Не цікаво»): межі пачки й причина."""

from domain.shared.errors import InvalidValue

# Скільки вакансій ховає один виклик і яка найдовша причина.
MAX_DISMISS_BATCH = 50
MAX_DISMISS_REASON_LENGTH = 200
DISMISS_REASON_NOT_INTERESTED = "не цікаво"
# Причина, з якою ховається список «уже не проходять фільтр» профілю.
DISMISS_REASON_PROFILE_FILTER = "фільтр профілю"


def parse_dismiss_reason(reason: str) -> str:
    """Причина приховування: непорожня, пробіли зведено до одного, не довша за ліміт."""
    cleaned = " ".join(reason.split())
    if not cleaned:
        raise InvalidValue("reason", "Вкажи причину приховування.")
    if len(cleaned) > MAX_DISMISS_REASON_LENGTH:
        raise InvalidValue(
            "reason", f"Причина задовга: більше {MAX_DISMISS_REASON_LENGTH} символів."
        )
    return cleaned
