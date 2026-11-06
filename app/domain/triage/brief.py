"""Текст вакансії для агента: лише секції вимог, якщо їх розпізнано, інакше весь текст."""

from dataclasses import dataclass
from enum import StrEnum

from domain.triage.sections import split_sections


class TextScope(StrEnum):
    REQUIREMENTS = "requirements"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class AgentText:
    text: str
    scope: TextScope


def agent_text(text: str) -> AgentText:
    """Секції «вимоги» і «буде плюсом», якщо парсер їх розпізнав і вони не порожні; інакше весь текст."""
    sections = split_sections(text)
    parts = []
    if sections.must:
        parts.append(f"Requirements:\n{sections.must}")
    if sections.nice:
        parts.append(f"Nice to have:\n{sections.nice}")
    if not parts:
        return AgentText(text, TextScope.FULL)
    return AgentText("\n\n".join(parts), TextScope.REQUIREMENTS)
