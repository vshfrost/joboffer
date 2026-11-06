"""In-memory адаптер пакета до інтерв'ю для core-тестів: та сама семантика, що в Postgres (версії
окремо для кожної вакансії, номери на користувача, commit).

Ділить `Store` із фейком вакансій, `PrepStore` із фейком тем і `FactStore` із фейком фактів.
"""

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Self

from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.prep.ids import KitId
from domain.prep.kit import InterviewKit, KitVersion
from tests.support.facts import InMemoryFacts
from tests.support.facts import Store as FactStore
from tests.support.jobs import Store
from tests.support.prep import InMemoryPrepUnitOfWork, PrepStore


@dataclass
class KitStore:
    # (користувач, номер вакансії) → версії від першої.
    kits: dict[tuple[UserId, int], list[KitVersion]]
    # Останній виданий номер версії користувача.
    counters: dict[UserId, int]

    @classmethod
    def empty(cls) -> Self:
        return cls({}, {})

    def copy(self) -> Self:
        return type(self)(
            {key: list(versions) for key, versions in self.kits.items()},
            dict(self.counters),
        )


class InMemoryInterviewKits:
    def __init__(self, kits: KitStore, jobs: Store) -> None:
        self._k = kits
        self._j = jobs

    def _number_of(self, user_id: UserId, job_id: JobId) -> int:
        for (owner, number), job in self._j.jobs.items():
            if owner == user_id and job.id == job_id:
                return number
        raise AssertionError("вакансію перевіряє use case")

    async def add(
        self,
        user_id: UserId,
        kit_id: KitId,
        job_id: JobId,
        kit: InterviewKit,
        now: datetime,
    ) -> KitVersion:
        job_number = self._number_of(user_id, job_id)
        number = self._k.counters.get(user_id, 0) + 1
        self._k.counters[user_id] = number
        versions = self._k.kits.setdefault((user_id, job_number), [])
        saved = KitVersion(kit_id, number, job_number, len(versions) + 1, kit, now)
        versions.append(saved)
        return saved

    async def latest(self, user_id: UserId, job_id: JobId) -> KitVersion | None:
        versions = self._k.kits.get((user_id, self._number_of(user_id, job_id)))
        return versions[-1] if versions else None


class InMemoryKitUnitOfWork(InMemoryPrepUnitOfWork):
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(
        self, store: Store, prep: PrepStore, facts: FactStore, kits: KitStore
    ) -> None:
        super().__init__(store, prep)
        self._facts = facts
        self._kits = kits
        self._staged_kits: KitStore | None = None

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self._staged_kits = self._kits.copy()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged_kits = None
        await super().__aexit__(exc_type, exc, traceback)

    @property
    def facts(self) -> InMemoryFacts:
        return InMemoryFacts(self._facts)

    @property
    def interview_kits(self) -> InMemoryInterviewKits:
        if self._staged_kits is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemoryInterviewKits(self._staged_kits, self._open()[0])

    async def commit(self) -> None:
        await super().commit()
        if self._staged_kits is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        self._kits.kits = self._staged_kits.kits
        self._kits.counters = self._staged_kits.counters
