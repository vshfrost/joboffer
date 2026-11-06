"""Use cases аналізу вакансії. REST і MCP викликають саме їх — правила в одному місці.

Claude отримує бриф (текст, профіль, підтверджені факти, рубрику), пише аналіз, сервер валідує й
застосовує жорсткі фільтри профілю. `flags` — знімок на момент збереження: зміна профілю їх не
переписує, а лише позначає аналіз застарілим. Вакансія скрізь — за номером у межах користувача.
"""

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime

from application.contracts.actor import Actor
from application.contracts.analysis import (
    AnalysisBriefData,
    AnalysisData,
    AnalysisInput,
    AnsweredGapData,
    GapAnswerData,
    GapAnswerInput,
    GapData,
    GapInput,
    KeywordFactsData,
)
from application.contracts.facts import FactData, FactInput
from application.facts.use_cases import fact_data
from application.jobs.use_cases import job_data
from application.ports.analysis import AnalysisUnitOfWork
from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.prompts import PromptKey, Prompts
from application.profile.use_cases import profile_data
from domain.analysis.analysis import Analysis, Gap, JobAnalysis, apply_filters
from domain.analysis.gap_answer import GapAnswer, validate_answer
from domain.analysis.ids import AnalysisId, GapAnswerId
from domain.analysis.rubric import rubric_values
from domain.facts.fact import Fact, FactSource, NewFact
from domain.facts.ids import FactId
from domain.facts.library import ordered, require_existing
from domain.shared.errors import InvalidValue, NotFound
from domain.shared.fingerprint import text_fingerprint


class AnalysisUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], AnalysisUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        prompts: Prompts,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids
        self._prompts = prompts

    async def prepare_analysis(
        self, actor: Actor, job_number: int
    ) -> AnalysisBriefData:
        """Бриф для аналізу. `NotFound` — вакансії нема чи вона чужа; `InvalidValue` — вакансія
        без тексту (з листа-алерту)."""
        user = actor.user_id
        async with self._unit_of_work() as uow:
            job = await uow.jobs.get(user, job_number)
            if job is None:
                raise _not_found(job_number)
            if job.needs_text:
                raise InvalidValue(
                    "job_id",
                    f"У вакансії {job_number} нема тексту опису "
                    "(вона з листа-алерту): спершу додай текст.",
                )
            facts = [fact for fact in await uow.facts.all(user) if fact.confirmed]
            profile = await uow.profiles.get(user)
            previous = await uow.analyses.get(user, job.id)
            answers = await uow.gap_answers.for_job(user, job.id)
        values = rubric_values(profile)
        return AnalysisBriefData(
            job=job_data(job, None),
            profile=profile_data(profile),
            confirmed_facts=tuple(_fact_data(fact) for fact in ordered(facts)),
            rubric=self._prompts.get(PromptKey.ANALYSIS_RUBRIC).format_map(
                {
                    "candidate": values.candidate,
                    "domain_examples": values.domain_examples,
                }
            ),
            previous=None if previous is None else analysis_data(previous, None),
            gap_answers=tuple(gap_answer_data(answer) for answer in answers),
        )

    async def save_analysis(
        self, actor: Actor, job_number: int, data: AnalysisInput
    ) -> AnalysisData:
        """Валідує аналіз, застосовує фільтри поточного профілю й замінює попередній.
        `InvalidValue` — нічого не збережено; `NotFound` — вакансії нема чи вона чужа."""
        analysis = JobAnalysis.parse(
            score=data.score,
            summary=data.summary,
            must_have=data.must_have,
            nice_to_have=data.nice_to_have,
            keywords=data.keywords,
            candidate_asks=data.candidate_asks,
            seniority=data.seniority,
            work_mode=data.work_mode,
            location=data.location,
            languages=data.languages,
            salary_min_eur=data.salary_min_eur,
            salary_max_eur=data.salary_max_eur,
            relocation=data.relocation,
            reasons=data.reasons,
            gaps=[
                Gap(item.gap, item.question) if isinstance(item, GapInput) else item
                for item in data.gaps
            ],
            keyword_facts=data.keyword_facts,
        )
        user = actor.user_id
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            job = await uow.jobs.get(user, job_number)
            if job is None:
                raise _not_found(job_number)
            if analysis.keyword_facts:
                require_existing(
                    {fact.number for fact in await uow.facts.all(user)},
                    [n for item in analysis.keyword_facts for n in item.fact_numbers],
                    "keyword_facts",
                )
            profile = await uow.profiles.get(user)
            posting = "\n".join(filter(None, (job.title, job.company, job.text)))
            flags = apply_filters(analysis, profile, posting)
            await uow.analyses.save(
                user, AnalysisId(self._ids.new()), job.id, analysis, flags, now
            )
            await uow.commit()
        return analysis_data(Analysis(job_number, analysis, flags, now), None)

    async def answer_gap(
        self,
        actor: Actor,
        job_number: int,
        gap_number: int,
        data: GapAnswerInput,
    ) -> AnsweredGapData:
        """Записує відповідь користувача на прогалину аналізу (номер з 1).

        «Є досвід»: факти з відповіді зберігаються з джерелом chat, підтвердженими й прив'язаними
        до вакансії; факт, що вже є (той самий текст), не дублюється, а прив'язується й
        підтверджується; аналізи стають застарілими. «Немає досвіду»: зберігається лише
        відповідь. Повторна відповідь на ту саму прогалину замінює попередню. `InvalidValue` —
        відповідь суперечить собі чи факт некоректний; `NotFound` — вакансії, аналізу чи
        прогалини нема (чужа вакансія — теж). Нічого не збережено, коли є помилка."""
        validate_answer(has_experience=data.has_experience, fact_count=len(data.facts))
        facts = [
            _parse_chat_fact(item, position, job_number)
            for position, item in enumerate(data.facts)
        ]
        user = actor.user_id
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            job = await uow.jobs.get(user, job_number)
            if job is None:
                raise _not_found(job_number)
            saved = await uow.analyses.get(user, job.id)
            if saved is None:
                raise NotFound(f"Аналіз вакансії {job_number} не знайдено.")
            if not 1 <= gap_number <= len(saved.analysis.gaps):
                raise NotFound(
                    f"Прогалину {gap_number} вакансії {job_number} не знайдено."
                )
            gap = saved.analysis.gaps[gap_number - 1].gap
            numbers: list[int] = []
            await uow.facts.lock_additions(user)
            for fact in facts:
                number = await uow.facts.find_duplicate(user, fact.fingerprint)
                if number is None:
                    number = (
                        await uow.facts.add(user, FactId(self._ids.new()), fact, now)
                    ).number
                else:
                    await uow.facts.confirm(user, [number], now)
                if number not in numbers:
                    numbers.append(number)
            answer = GapAnswer(gap, data.has_experience, tuple(numbers), now)
            await uow.gap_answers.save(
                user, GapAnswerId(self._ids.new()), job.id, answer
            )
            if data.has_experience:
                await uow.profiles.mark_analysis_inputs_changed(user, now)
            await uow.commit()
            linked = [await uow.facts.get(user, number) for number in numbers]
        return AnsweredGapData(
            job_number=job_number,
            gap_number=gap_number,
            answer=gap_answer_data(answer),
            facts=tuple(fact_data(fact) for fact in linked if fact is not None),
        )

    async def get_analysis(self, actor: Actor, job_number: int) -> AnalysisData:
        """Збережений аналіз зі знаком застарілості. `NotFound` — вакансії чи аналізу нема."""
        user = actor.user_id
        async with self._unit_of_work() as uow:
            job = await uow.jobs.get(user, job_number)
            saved = None if job is None else await uow.analyses.get(user, job.id)
            answers = (
                []
                if job is None or saved is None
                else await uow.gap_answers.for_job(user, job.id)
            )
            changed_at = await uow.profiles.analysis_inputs_changed_at(user)
        if saved is None:
            raise NotFound(f"Аналіз вакансії {job_number} не знайдено.")
        stale = changed_at if changed_at and saved.updated_at < changed_at else None
        return analysis_data(saved, stale, answers)


def _parse_chat_fact(item: FactInput, position: int, job_number: int) -> NewFact:
    """Факт з відповіді в чаті: користувач схвалив його формулювання, тож він одразу підтверджений."""
    try:
        parsed = NewFact.parse(kind=item.kind, text=item.text, source=FactSource.CHAT)
    except InvalidValue as error:
        raise InvalidValue(
            f"facts.{position}.{error.field}", f"Факт {position + 1}: {error.message}"
        ) from error
    return replace(parsed, confirmed=True, job_number=job_number)


def _not_found(number: int) -> NotFound:
    return NotFound(f"Вакансію {number} не знайдено.")


def _fact_data(fact: Fact) -> FactData:
    return FactData(
        fact_number=fact.number,
        kind=fact.kind,
        text=fact.text,
        confirmed=fact.confirmed,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
    )


def _answer_data(answer: GapAnswer | None) -> GapAnswerData | None:
    return None if answer is None else gap_answer_data(answer)


def gap_answer_data(answer: GapAnswer) -> GapAnswerData:
    return GapAnswerData(
        gap=answer.gap,
        has_experience=answer.has_experience,
        fact_numbers=answer.fact_numbers,
        answered_at=answer.answered_at,
    )


def analysis_data(
    saved: Analysis,
    stale_since: datetime | None,
    answers: Sequence[GapAnswer] = (),
) -> AnalysisData:
    analysis = saved.analysis
    # Відповідь прив'язана до тексту прогалини (без регістру й зайвих пробілів), не до номера.
    by_gap = {text_fingerprint(answer.gap): answer for answer in answers}
    return AnalysisData(
        job_number=saved.job_number,
        score=analysis.score,
        summary=analysis.summary,
        must_have=analysis.must_have,
        nice_to_have=analysis.nice_to_have,
        keywords=analysis.keywords,
        candidate_asks=analysis.candidate_asks,
        seniority=analysis.seniority,
        work_mode=analysis.work_mode,
        location=analysis.location,
        languages=analysis.languages,
        salary_min_eur=analysis.salary_min_eur,
        salary_max_eur=analysis.salary_max_eur,
        relocation=analysis.relocation,
        reasons=analysis.reasons,
        gaps=tuple(
            GapData(
                number=number,
                gap=item.gap,
                question=item.question,
                answer=_answer_data(by_gap.get(text_fingerprint(item.gap))),
            )
            for number, item in enumerate(analysis.gaps, start=1)
        ),
        filters_passed=saved.filters_passed,
        flags=saved.flags,
        updated_at=saved.updated_at,
        stale_since=stale_since,
        keyword_facts=None
        if analysis.keyword_facts is None
        else tuple(
            KeywordFactsData(keyword=item.keyword, fact_numbers=item.fact_numbers)
            for item in analysis.keyword_facts
        ),
    )
