"""In-memory адаптер prep для core-тестів: та сама семантика, що в Postgres (slug, номери, commit).

Ділить `Store` із фейком вакансій: теми бачать ті самі вакансії й аналізи, що й список.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import TracebackType
from typing import Self

from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.prep.ids import StepId, TopicId
from domain.prep.plan import NewStep, PrepStep
from domain.prep.topic import NewTopic, PrepTopic, TopicJob
from tests.support.analysis import InMemoryAnalyses
from tests.support.documents import DocumentStore, InMemoryDocuments
from tests.support.facts import InMemoryFacts
from tests.support.facts import Store as FactStore
from tests.support.jobs import InMemoryJobs, Store


@dataclass
class PrepStore:
    topics: dict[tuple[UserId, int], PrepTopic]
    # Прив'язки: (користувач, номер теми) → {номер вакансії: прогалина}.
    links: dict[tuple[UserId, int], dict[int, str]]
    counters: dict[UserId, int]
    # Останній виданий номер кроку користувача: номери видалених кроків не повторюються.
    step_counters: dict[UserId, int] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> Self:
        return cls({}, {}, {})

    def copy(self) -> Self:
        return type(self)(
            dict(self.topics),
            {key: dict(gaps) for key, gaps in self.links.items()},
            dict(self.counters),
            dict(self.step_counters),
        )


class InMemoryPrepTopics:
    def __init__(self, prep: PrepStore, jobs: Store) -> None:
        self._p = prep
        self._j = jobs

    def _number_of(self, user_id: UserId, job_id: JobId) -> int:
        for (owner, number), job in self._j.jobs.items():
            if owner == user_id and job.id == job_id:
                return number
        raise AssertionError("вакансію перевіряє use case")

    async def save(
        self,
        user_id: UserId,
        topic_id: TopicId,
        job_id: JobId,
        topic: NewTopic,
        gap: str,
        now: datetime,
    ) -> int:
        existing = next(
            (
                saved
                for (owner, _), saved in self._p.topics.items()
                if owner == user_id and saved.slug == topic.slug
            ),
            None,
        )
        if existing is None:
            number = self._p.counters.get(user_id, 0) + 1
            self._p.counters[user_id] = number
            saved = PrepTopic(
                id=topic_id,
                number=number,
                slug=topic.slug,
                title=topic.title,
                kind=topic.kind,
                summary=topic.summary,
                deadline=topic.deadline,
                created_at=now,
            )
        else:
            number = existing.number
            saved = replace(
                existing,
                title=topic.title,
                kind=topic.kind,
                summary=topic.summary,
                deadline=topic.deadline,
            )
        key = (user_id, number)
        self._p.topics[key] = saved
        self._p.links.setdefault(key, {})[self._number_of(user_id, job_id)] = gap
        return number

    async def get(self, user_id: UserId, number: int) -> PrepTopic | None:
        found = [topic for topic in await self.all(user_id) if topic.number == number]
        return found[0] if found else None

    async def replace_pending_steps(
        self,
        user_id: UserId,
        topic_number: int,
        steps: Sequence[tuple[StepId, NewStep]],
    ) -> None:
        key = (user_id, topic_number)
        topic = self._p.topics[key]
        kept = [step for step in topic.steps if step.done_at is not None]
        position = max((step.position for step in kept), default=0)
        added = []
        for step_id, new in steps:
            position += 1
            number = self._p.step_counters.get(user_id, 0) + 1
            self._p.step_counters[user_id] = number
            added.append(
                PrepStep(
                    id=step_id,
                    number=number,
                    position=position,
                    kind=new.kind,
                    title=new.title,
                    minutes=new.minutes,
                    details=new.details,
                    resources=new.resources,
                )
            )
        self._p.topics[key] = replace(topic, steps=(*kept, *added))

    async def complete_step(
        self, user_id: UserId, step_number: int, note: str, now: datetime
    ) -> int | None:
        for (owner, number), topic in self._p.topics.items():
            if owner != user_id:
                continue
            for step in topic.steps:
                if step.number == step_number:
                    done = replace(
                        step, done_at=step.done_at or now, note=note or step.note
                    )
                    steps = tuple(done if s is step else s for s in topic.steps)
                    self._p.topics[(owner, number)] = replace(topic, steps=steps)
                    return number
        return None

    async def set_ready(
        self, user_id: UserId, topic_number: int, *, ready: bool, now: datetime
    ) -> None:
        key = (user_id, topic_number)
        topic = self._p.topics[key]
        ready_at = (topic.ready_at or now) if ready else None
        self._p.topics[key] = replace(topic, ready_at=ready_at)

    async def all(self, user_id: UserId) -> list[PrepTopic]:
        found = []
        for (owner, number), topic in sorted(
            self._p.topics.items(), key=lambda item: item[0][1]
        ):
            if owner != user_id:
                continue
            links = self._p.links[(owner, number)]
            jobs = []
            for job_number in sorted(links):
                job = self._j.jobs[(owner, job_number)]
                analysis = self._j.analyses[(owner, job_number)]
                jobs.append(
                    TopicJob(
                        job_number,
                        job.title,
                        job.company,
                        analysis.analysis.score,
                        links[job_number],
                    )
                )
            found.append(replace(topic, jobs=tuple(jobs)))
        return found


class InMemoryPrepUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(
        self,
        store: Store,
        prep: PrepStore,
        facts: FactStore | None = None,
        documents: DocumentStore | None = None,
    ) -> None:
        self._store = store
        self._prep = prep
        self._facts = facts if facts is not None else FactStore.empty()
        self._documents = documents if documents is not None else DocumentStore.empty()
        self._staged: tuple[Store, PrepStore] | None = None

    def _open(self) -> tuple[Store, PrepStore]:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged

    @property
    def jobs(self) -> InMemoryJobs:
        return InMemoryJobs(self._open()[0])

    @property
    def analyses(self) -> InMemoryAnalyses:
        return InMemoryAnalyses(self._open()[0])

    @property
    def prep_topics(self) -> InMemoryPrepTopics:
        store, prep = self._open()
        return InMemoryPrepTopics(prep, store)

    @property
    def facts(self) -> InMemoryFacts:
        return InMemoryFacts(self._facts)

    @property
    def documents(self) -> InMemoryDocuments:
        return InMemoryDocuments(self._open()[0], self._documents)

    async def __aenter__(self) -> Self:
        self._staged = (self._store.copy(), self._prep.copy())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        _, prep = self._open()
        self._prep.topics = prep.topics
        self._prep.links = prep.links
        self._prep.counters = prep.counters
        self._prep.step_counters = prep.step_counters
