"""Світ для core-тестів подач: вакансії й подачі над одним in-memory сховищем."""

from datetime import UTC, datetime

from anyio.from_thread import BlockingPortal

from application.applications.use_cases import ApplicationUseCases
from application.contracts.actor import Actor, Channel, Scope
from application.contracts.applications import ApplicationData, ApplicationInput
from application.contracts.jobs import JobData, JobInput, JobSearchInput
from application.jobs.use_cases import JobUseCases
from domain.identity.ids import UserId
from tests.support.clock import FakeClock
from tests.support.documents import DocumentStore, InMemoryDocuments
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store

# 23:30 UTC 1 березня — у Мадриді вже 2 березня 00:30: «сьогодні» там і в UTC різні дні.
MADRID_AFTER_MIDNIGHT = datetime(2026, 3, 1, 23, 30, tzinfo=UTC)


class InMemoryApplicationUnitOfWork(InMemoryJobUnitOfWork):
    """Вакансії й подачі зі stage-ом, як в `InMemoryJobUnitOfWork`, плюс документи лише для читання
    (подача бере з них версію CV; зберігає документи `DocumentUseCases` в іншому UoW)."""

    def __init__(self, store: Store, documents: DocumentStore | None = None) -> None:
        super().__init__(store)
        self._documents = documents if documents is not None else DocumentStore.empty()

    @property
    def documents(self) -> InMemoryDocuments:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemoryDocuments(self._staged, self._documents)


class ApplicationWorld:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.store = Store.empty()
        self.alice = self._actor()
        self.bob = self._actor()
        self.jobs = JobUseCases(lambda: InMemoryJobUnitOfWork(self.store), clock, ids)
        self.applications = ApplicationUseCases(
            lambda: InMemoryApplicationUnitOfWork(self.store), clock
        )

    def _actor(self) -> Actor:
        return Actor(
            user_id=UserId(self.ids.new()),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )

    def add_job(self, actor: Actor, text: str = "Backend engineer") -> int:
        added = self.portal.call(self.jobs.add_job, actor, JobInput(text=text))
        return added.job_number

    def mark(
        self, actor: Actor, job: int, channel: str = "email", **fields: object
    ) -> ApplicationData:
        data = ApplicationInput(channel=channel, **fields)  # type: ignore[arg-type]
        return self.portal.call(self.applications.mark_applied, actor, job, data)

    def move(self, actor: Actor, job: int, status: str) -> ApplicationData:
        return self.portal.call(
            self.applications.set_application_status, actor, job, status
        )

    def application(self, actor: Actor, job: int) -> ApplicationData | None:
        return self.portal.call(self.applications.get_application, actor, job)

    def job(self, actor: Actor, job: int) -> JobData:
        return self.portal.call(self.jobs.get_job, actor, job)

    def dismiss(self, actor: Actor, numbers: list[int]) -> None:
        self.portal.call(self.jobs.dismiss_jobs, actor, numbers, "не цікаво")

    def listed(self, actor: Actor, **fields: object) -> list[int]:
        data = JobSearchInput(**fields)  # type: ignore[arg-type]
        found = self.portal.call(self.jobs.list_jobs, actor, data)
        return [item.job_number for item in found]
