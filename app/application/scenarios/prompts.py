"""Порт `Prompts` з однаковим хвостом «запропонуй наступний крок» у промптах сценаріїв.

Хвіст дописується до кожного кроку ланцюжка, крім останнього (`apply`): і для `get_scenario`
(MCP), і для `GET /api/prompts` (веб), бо обидва беруть промпти з цього порту.
"""

from application.ports.prompts import PromptKey, Prompts

TAILED_KEYS = frozenset(
    {
        PromptKey.REQUEST_ADD_JOB,
        PromptKey.REQUEST_ANALYSIS,
        PromptKey.REQUEST_GAPS,
        PromptKey.REQUEST_REANALYSIS,
        PromptKey.REQUEST_CV,
        PromptKey.REQUEST_COVER_LETTER,
    }
)


class ScenarioPrompts:
    def __init__(self, inner: Prompts) -> None:
        self._inner = inner

    def get(self, key: PromptKey) -> str:
        text = self._inner.get(key)
        if key not in TAILED_KEYS:
            return text
        return f"{text}\n\n{self._inner.get(PromptKey.SCENARIO_NEXT_STEP)}"
