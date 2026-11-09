"""Покриття must-have вимог аналізу рядками CV: агент називає, які факти стоять під пунктом (прямо чи
як аналог), сервер перевіряє, що факти справжні й що CV на них справді спирається."""

from enum import StrEnum


class MustHaveKind(StrEnum):
    """Як факти закривають пункт: самі вимоги (`fact`) чи схожий досвід замість неї (`analogue`)."""

    FACT = "fact"
    ANALOGUE = "analogue"


class MustHaveStatus(StrEnum):
    COVERED = "covered"
    ANALOGUE = "analogue"
    MISSING = "missing"
