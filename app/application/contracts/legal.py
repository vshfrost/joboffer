"""Юридичні документи: умови та політика конфіденційності."""

from dataclasses import dataclass
from enum import StrEnum


class LegalDoc(StrEnum):
    """Значення — ім'я файлу `templates/legal/<doc>.md` і сегмент адреси."""

    TERMS = "terms"
    PRIVACY = "privacy"


@dataclass(frozen=True, slots=True)
class LegalDocument:
    doc: LegalDoc
    version: str
    text: str
