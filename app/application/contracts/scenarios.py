"""Результат `get_scenario`: примітиви (значення будує use case)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class ScenarioData:
    """`next` — наступний крок ланцюжка з урахуванням пропусків (None після останнього);
    `skip_reason` — чому цей крок для вакансії не потрібен (None — потрібен)."""

    name: str
    prompt: str
    next: str | None
    skip_reason: str | None
