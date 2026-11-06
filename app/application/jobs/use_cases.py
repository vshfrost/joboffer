"""Use cases вакансій. REST і MCP викликають саме їх — правила в одному місці.

Вакансія скрізь — за номером у межах користувача; чужа й неіснуюча не відрізняються.
"""

from collections.abc import Callable, Sequence
from typing import cast

from application.applications.use_cases import application_data
from application.contracts.actor import Actor
from application.contracts.jobs import (
    AddedJob,
    AddOutcome,
    JobData,
    JobInput,
    JobSearchInput,
    JobSummaryData,
    JobTabCountsData,
)
from application.contracts.triage import triage_data
from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.jobs import JobUnitOfWork
from domain.applications.application import Application
from domain.applications.errors import JobHasApplication
from domain.identity.ids import UserId
from domain.jobs.dismiss import MAX_DISMISS_BATCH, parse_dismiss_reason
from domain.jobs.ids import JobId
from domain.jobs.job import Job, JobSummary, NewJob
from domain.jobs.search import JobSearch, JobSearchDraft
from domain.shared.errors import InvalidValue, NotFound
from domain.triage.triage import Triage


class JobUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], JobUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids

    async def add_job(self, actor: Actor, data: JobInput) -> AddedJob:
        """Додає вакансію. Дубль не створюється — повертається наявна. Посилання LinkedIn на
        вакансію, що чекає на текст (з листа-алерту), дописує в неї опис (назва й компанія
        лишаються). `InvalidFields` — нічого не збережено."""
        job = NewJob.parse(
            text=data.text, url=data.url, title=data.title, company=data.company
        )
        user = actor.user_id
        async with self._unit_of_work() as uow:
            await uow.jobs.lock_additions(user)
            if job.linkedin_id is not None:
                waiting = await self._waiting_for_text(uow, user, job.linkedin_id)
                if waiting is not None:
                    # Той самий текст уже є в іншій вакансії — це дубль тієї, не цієї.
                    same_text = await uow.jobs.find_duplicate(
                        user, NewJob(text=job.text)
                    )
                    if same_text is not None:
                        return AddedJob(same_text, AddOutcome.DUPLICATE)
                    # `parse` гарантує непорожній текст.
                    await uow.jobs.complete_text(user, waiting, cast("str", job.text))
                    await uow.commit()
                    return AddedJob(waiting, AddOutcome.TEXT_ADDED)
            existing = await uow.jobs.find_duplicate(user, job)
            if existing is not None:
                return AddedJob(existing, AddOutcome.DUPLICATE)
            number = await uow.jobs.add(
                user, JobId(self._ids.new()), job, self._clock.now()
            )
            await uow.commit()
        return AddedJob(number, AddOutcome.CREATED)

    async def get_job(self, actor: Actor, job_number: int) -> JobData:
        async with self._unit_of_work() as uow:
            job = await uow.jobs.get(actor.user_id, job_number)
            if job is None:
                raise _not_found(job_number)
            triage = await uow.jobs.get_triage(actor.user_id, job_number)
            application = await uow.applications.get(actor.user_id, job_number)
        return job_data(job, triage, application)

    async def open_job(self, actor: Actor, job_number: int) -> JobData:
        """Деталі вакансії для людини у вебі: перше відкриття ставить час і знімає «нове»
        (повторне його не змінює). `NotFound` — нема чи чужа."""
        async with self._unit_of_work() as uow:
            job = await uow.jobs.get(actor.user_id, job_number)
            if job is None:
                raise _not_found(job_number)
            if job.opened_at is None:
                await uow.jobs.mark_opened(actor.user_id, job_number, self._clock.now())
                await uow.commit()
                job = await uow.jobs.get(actor.user_id, job_number) or job
            triage = await uow.jobs.get_triage(actor.user_id, job_number)
            application = await uow.applications.get(actor.user_id, job_number)
        return job_data(job, triage, application)

    async def list_jobs(
        self, actor: Actor, data: JobSearchInput
    ) -> list[JobSummaryData]:
        """`InvalidFields` — некоректні фільтри."""
        search = JobSearch.parse(
            JobSearchDraft(
                query=data.query,
                days=data.days,
                source=data.source,
                needs_text=data.needs_text,
                dismissed=data.dismissed,
                work_mode=data.work_mode,
                triage_verdict=data.triage_verdict,
                status=data.status,
                stage=data.stage,
                hide_rejected=data.hide_rejected,
                limit=data.limit,
            ),
            self._clock.now(),
        )
        async with self._unit_of_work() as uow:
            found = await uow.jobs.search(actor.user_id, search)
        return [_summary_data(item) for item in found]

    async def tab_counts(self, actor: Actor) -> JobTabCountsData:
        """Лічильники табів вебу: не залежать від фільтрів списку й від його ліміту."""
        async with self._unit_of_work() as uow:
            counts = await uow.jobs.tab_counts(actor.user_id)
        return JobTabCountsData(
            in_progress=counts.in_progress,
            applied_unreviewed=counts.applied_unreviewed,
            needs_text=counts.needs_text,
        )

    async def job_sources(self, actor: Actor) -> list[str]:
        async with self._unit_of_work() as uow:
            return await uow.jobs.sources(actor.user_id)

    async def dismiss_jobs(
        self, actor: Actor, job_numbers: Sequence[int], reason: str
    ) -> None:
        """Ховає вакансії зі списку («Не цікаво»): усе або нічого. Сховану повторно не чіпає
        (причина лишається перша). `InvalidValue` (з номером елемента, якщо їх кілька) —
        порожня чи надто велика пачка, причина порожня чи задовга, повтор, вакансії нема / чужа;
        `JobHasApplication` — на вакансію є подача (поданих не ховають)."""
        reason = parse_dismiss_reason(reason)
        if not job_numbers:
            raise InvalidValue("job_ids", "Порожня пачка: потрібна хоч одна вакансія.")
        if len(job_numbers) > MAX_DISMISS_BATCH:
            raise InvalidValue(
                "job_ids", f"У пачці не більше {MAX_DISMISS_BATCH} вакансій."
            )
        async with self._unit_of_work() as uow:
            first_seen: dict[int, int] = {}
            for position, number in enumerate(job_numbers, start=1):
                where = f"Елемент {position}: " if len(job_numbers) > 1 else ""
                if number in first_seen:
                    raise _item_error(
                        where,
                        f"вакансія {number} уже є в елементі {first_seen[number]}.",
                    )
                first_seen[number] = position
                if await uow.jobs.get(actor.user_id, number) is None:
                    raise _item_error(where, f"вакансію {number} не знайдено.")
                if await uow.applications.get(actor.user_id, number) is not None:
                    raise JobHasApplication(
                        _item_message(
                            where,
                            f"на вакансію {number} уже є подача — поданих вакансій не ховають.",
                        )
                    )
            await uow.jobs.dismiss(
                actor.user_id, list(job_numbers), reason, self._clock.now()
            )
            await uow.commit()

    async def restore_job(self, actor: Actor, job_number: int) -> None:
        """Повертає сховану вакансію в список; не сховану не змінює. `NotFound` — нема чи чужа."""
        async with self._unit_of_work() as uow:
            if await uow.jobs.get(actor.user_id, job_number) is None:
                raise _not_found(job_number)
            await uow.jobs.restore(actor.user_id, job_number)
            await uow.commit()

    @staticmethod
    async def _waiting_for_text(
        uow: JobUnitOfWork, user: UserId, linkedin_id: str
    ) -> int | None:
        """Вакансія користувача з цим LinkedIn id у стані «потрібен текст» (з листа-алерту)."""
        number = await uow.jobs.find_linkedin(user, linkedin_id)
        if number is None:
            return None
        job = await uow.jobs.get(user, number)
        return number if job is not None and job.needs_text else None


def _not_found(number: int) -> NotFound:
    return NotFound(f"Вакансію {number} не знайдено.")


def _item_message(where: str, message: str) -> str:
    """Повідомлення з номером елемента пачки; для одиночної вакансії — просто з великої літери."""
    return where + message if where else message[0].upper() + message[1:]


def _item_error(where: str, message: str) -> InvalidValue:
    return InvalidValue("job_ids", _item_message(where, message))


def job_data(
    job: Job, triage: Triage | None, application: Application | None = None
) -> JobData:
    return JobData(
        job_number=job.number,
        source=job.source,
        url=job.url,
        title=job.title,
        company=job.company,
        location=job.location,
        text=job.text,
        created_at=job.created_at,
        needs_text=job.needs_text,
        dismissed_at=job.dismissed_at,
        dismiss_reason=job.dismiss_reason,
        opened_at=job.opened_at,
        is_new=job.is_new,
        triage=None if triage is None else triage_data(triage),
        application=None if application is None else application_data(application),
    )


def _summary_data(summary: JobSummary) -> JobSummaryData:
    return JobSummaryData(
        job_number=summary.number,
        source=summary.source,
        url=summary.url,
        title=summary.title,
        company=summary.company,
        created_at=summary.created_at,
        needs_text=summary.needs_text,
        dismissed=summary.dismissed,
        score=summary.score,
        filters_passed=summary.filters_passed,
        work_mode=summary.work_mode,
        triage_score=summary.triage_score,
        triage_verdict=summary.triage_verdict,
        triage_reason=summary.triage_reason,
        status=summary.status,
        is_new=summary.is_new,
    )
