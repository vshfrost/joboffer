"""Use cases подач. REST і MCP викликають саме їх — правила в одному місці.

Користувач позначає вакансію поданою і веде подачу воронкою. Вакансія скрізь — за номером
у межах користувача; чужа й неіснуюча не відрізняються.
"""

from collections.abc import Callable
from dataclasses import replace

from application.contracts.actor import Actor
from application.contracts.applications import (
    ApplicationData,
    ApplicationInput,
    CvFunnelData,
    CvFunnelRowData,
    CvVersionData,
)
from application.ports.application_records import ApplicationUnitOfWork
from application.ports.clock import Clock
from domain.applications.application import (
    Application,
    CvVersion,
    NewApplication,
    allowed_transitions,
    check_transition,
    parse_status,
)
from domain.applications.funnel import cv_funnel
from domain.documents.document import Document, DocumentKind
from domain.shared.errors import NotFound
from domain.shared.local_time import local_today


class ApplicationUseCases:
    def __init__(
        self, unit_of_work: Callable[[], ApplicationUnitOfWork], clock: Clock
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def mark_applied(
        self, actor: Actor, job_number: int, data: ApplicationInput
    ) -> ApplicationData:
        """Позначає вакансію поданою (статус `applied`). Повторно — замінює деталі, статус
        лишається. Дата за замовчуванням — сьогодні за Мадридом; сховану вакансію повертає
        в список. `InvalidFields` — деталі не пройшли перевірку (нічого не змінено);
        `NotFound` — вакансії нема чи вона чужа. Подача запам'ятовує версію CV, актуальну на
        цей момент (номер, день збереження, покриття слів); нове збереження CV її не змінює,
        повторне позначення — оновлює. CV нема — версія «невідома»."""
        now = self._clock.now()
        details = NewApplication.parse(
            applied_on=data.applied_on,
            today=local_today(now),
            channel=data.channel,
            ats=data.ats,
            company_domains=data.company_domains,
            company_emails=data.company_emails,
        )
        async with self._unit_of_work() as uow:
            job = await uow.jobs.get(actor.user_id, job_number)
            if job is None:
                raise NotFound(f"Вакансію {job_number} не знайдено.")
            # Подану вакансію не ховають: якщо її сховано, вона повертається в список.
            await uow.jobs.restore(actor.user_id, job_number)
            documents = await uow.documents.list_for_job(actor.user_id, job.id)
            details = replace(details, cv=_current_cv(documents))
            saved = await uow.applications.save(actor.user_id, job_number, details, now)
            await uow.commit()
        return application_data(saved)

    async def set_application_status(
        self, actor: Actor, job_number: int, status: str
    ) -> ApplicationData:
        """Новий статус подачі: лише вперед; той самий — без змін. `InvalidValue` — невідомий
        статус, перехід назад чи з закритої подачі; `NotFound` — подачі нема (чи вона чужа)."""
        new = parse_status(status)
        async with self._unit_of_work() as uow:
            current = await uow.applications.get(actor.user_id, job_number)
            if current is None:
                raise NotFound(
                    f"Подачі на вакансію {job_number} нема: спершу mark_applied."
                )
            if not check_transition(current.status, new):
                return application_data(current)
            moved = await uow.applications.set_status(
                actor.user_id, job_number, new, self._clock.now()
            )
            await uow.commit()
        return application_data(moved)

    async def get_application(
        self, actor: Actor, job_number: int
    ) -> ApplicationData | None:
        """Подача на вакансію; None — вакансії нема, вона чужа або на неї не подавались."""
        async with self._unit_of_work() as uow:
            found = await uow.applications.get(actor.user_id, job_number)
        return None if found is None else application_data(found)

    async def cv_funnel(self, actor: Actor) -> CvFunnelData:
        """Звіт воронки за версіями CV: подачі, відповіді й інтервʼю окремо для кожної версії;
        подачі без версії — однією групою «невідомо» (`cv_number` None)."""
        async with self._unit_of_work() as uow:
            found = await uow.applications.list_all(actor.user_id)
        return CvFunnelData(
            rows=tuple(
                CvFunnelRowData(
                    cv_number=None if row.cv is None else row.cv.number,
                    saved_on=None if row.cv is None else row.cv.saved_on,
                    coverage_percent=None
                    if row.cv is None
                    else row.cv.coverage_percent,
                    applications=row.applications,
                    replies=row.replies,
                    interviews=row.interviews,
                )
                for row in cv_funnel(found)
            )
        )


def _current_cv(documents: list[Document]) -> CvVersion | None:
    """Останнє CV вакансії (список — новіші першими) як версія для подачі; CV нема — None."""
    latest = next((item for item in documents if item.kind is DocumentKind.CV), None)
    if latest is None:
        return None
    keywords = None if latest.lint is None else latest.lint.keywords
    return CvVersion(
        number=latest.number,
        saved_on=local_today(latest.created_at),
        coverage_percent=None if keywords is None else keywords.percent,
    )


def application_data(application: Application) -> ApplicationData:
    cv = application.cv
    return ApplicationData(
        job_number=application.job_number,
        status=application.status,
        applied_on=application.applied_on,
        channel=application.channel,
        ats=application.ats,
        company_domains=application.company_domains,
        company_emails=application.company_emails,
        status_changed_at=application.status_changed_at,
        allowed_transitions=allowed_transitions(application.status),
        cv=None
        if cv is None
        else CvVersionData(
            number=cv.number,
            saved_on=cv.saved_on,
            coverage_percent=cv.coverage_percent,
        ),
    )
