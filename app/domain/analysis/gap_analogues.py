"""Аналоги прогалин аналізу: які підтверджені факти кандидата ближче за все до того, чого вакансія
просить, а в кандидата нема. Агент пише їх в аналізі, щоб CV не шукало аналоги вдруге.
Прогалина без жодного аналога — `no_honest_analogue`: чесного аналога нема."""

from dataclasses import dataclass

MAX_ANALOGUES = 5


@dataclass(frozen=True, slots=True)
class Analogue:
    """Один аналог: номери фактів і коротке пояснення, чим вони споріднені з прогалиною."""

    fact_numbers: tuple[int, ...]
    explanation: str


@dataclass(frozen=True, slots=True)
class GapAnalogues:
    """Аналоги однієї прогалини; порожній список — `no_honest_analogue`."""

    gap: str
    analogues: tuple[Analogue, ...] = ()

    @property
    def no_honest_analogue(self) -> bool:
        return not self.analogues
