"""Use case `get_scenario`: промпт сценарію й наступний крок ланцюжка для вакансії.

Порядок і пропуски — у домені (`domain.scenarios`); тут лише дізнаємось, що відомо про вакансію
(відкриті прогалини, застарілий аналіз), і підставляємо номер вакансії в промпт. Вакансія — за
номером у межах користувача; чужа й неіснуюча не відрізняються.
"""

from application.analysis.use_cases import AnalysisUseCases
from application.contracts.actor import Actor
from application.contracts.scenarios import ScenarioData
from application.jobs.use_cases import JobUseCases
from application.ports.prompts import PromptKey, Prompts
from domain.scenarios.chain import (
    JobProgress,
    Scenario,
    next_after,
    parse_scenario,
    skip_reason,
)
from domain.shared.errors import InvalidValue, NotFound

PROMPT_KEYS = {
    Scenario.ADD_JOB: PromptKey.REQUEST_ADD_JOB,
    Scenario.ANALYSIS: PromptKey.REQUEST_ANALYSIS,
    Scenario.GAPS: PromptKey.REQUEST_GAPS,
    Scenario.REANALYSIS: PromptKey.REQUEST_REANALYSIS,
    Scenario.CV: PromptKey.REQUEST_CV,
    Scenario.COVER_LETTER: PromptKey.REQUEST_COVER_LETTER,
    Scenario.APPLY: PromptKey.REQUEST_APPLY,
}

# Вакансії ще нема: пропусків не буде, бо вони стосуються лише кроків після аналізу.
NO_JOB = JobProgress(has_open_gaps=False, analysis_stale=False)


class ScenarioUseCases:
    def __init__(
        self, jobs: JobUseCases, analysis: AnalysisUseCases, prompts: Prompts
    ) -> None:
        self._jobs = jobs
        self._analysis = analysis
        self._prompts = prompts

    async def get_scenario(
        self, actor: Actor, name: str, job_number: int | None = None
    ) -> ScenarioData:
        """`InvalidValue` — невідоме ім'я чи нема job_id для кроку, що його потребує;
        `NotFound` — вакансії нема чи вона чужа."""
        scenario = parse_scenario(name)
        if job_number is None:
            if scenario is not Scenario.ADD_JOB:
                raise InvalidValue(
                    "job_id", f"Сценарій {scenario.value} потребує job_id вакансії."
                )
            progress = NO_JOB
            prompt = self._prompts.get(PROMPT_KEYS[scenario])
        else:
            progress = await self._progress(actor, job_number)
            prompt = self._prompts.get(PROMPT_KEYS[scenario]).replace(
                "{job_id}", str(job_number)
            )
        following = next_after(scenario, progress)
        return ScenarioData(
            name=scenario.value,
            prompt=prompt,
            next=None if following is None else following.value,
            skip_reason=skip_reason(scenario, progress),
        )

    async def _progress(self, actor: Actor, job_number: int) -> JobProgress:
        await self._jobs.get_job(actor, job_number)
        try:
            analysis = await self._analysis.get_analysis(actor, job_number)
        except NotFound:
            return NO_JOB
        return JobProgress(
            has_open_gaps=any(gap.answer is None for gap in analysis.gaps),
            analysis_stale=analysis.stale_since is not None,
        )
