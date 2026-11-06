"""Ключове слово аналізу — вимога вакансії; кілька написань однієї вимоги пишуться через «|»
(`Java | TypeScript | Python`, `gestión de estado | state management`) і рахуються за одну.
Слово без «|» — вимога з одним написанням, як у старих аналізах."""

from dataclasses import dataclass

SEPARATOR = "|"
MAX_SPELLINGS = 5


def spellings(keyword: str) -> tuple[str, ...]:
    """Написання вимоги без зайвих пробілів; порожнє між «|» лишається порожнім рядком."""
    return tuple(part.strip() for part in keyword.split(SEPARATOR))


def requirement_key(keyword: str) -> frozenset[str]:
    """Вимога без урахування регістру, пробілів і порядку написань: однакова в «Java | Python»
    і «python|JAVA». За нею слово з карти фактів знаходить свою вимогу."""
    return frozenset(
        " ".join(part.split()).casefold() for part in spellings(keyword) if part
    )


def tidy(keyword: str) -> str:
    """Один пробіл навколо кожного «|»; група з порожнім написанням лишається як є."""
    parts = spellings(keyword)
    return " | ".join(parts) if all(parts) else keyword


@dataclass(frozen=True, slots=True)
class KeywordFacts:
    """Які факти (номери) стоять під ключовим словом аналізу."""

    keyword: str
    fact_numbers: tuple[int, ...]
