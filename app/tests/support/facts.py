"""In-memory адаптер facts для core-тестів: та сама семантика, що в Postgres (номери, дублі, commit)."""

from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import datetime
from types import TracebackType
from typing import Self

from domain.facts.fact import Fact, NewFact, NewOriginalCv, OriginalCv
from domain.facts.ids import FactId
from domain.identity.ids import UserId


@dataclass
class Store:
    facts: dict[tuple[UserId, int], Fact]
    hashes: dict[tuple[UserId, int], str]
    counters: dict[UserId, int]
    cvs: dict[UserId, OriginalCv]

    @classmethod
    def empty(cls) -> Self:
        return cls({}, {}, {}, {})

    def copy(self) -> Self:
        return type(self)(
            dict(self.facts), dict(self.hashes), dict(self.counters), dict(self.cvs)
        )


class InMemoryFacts:
    def __init__(self, store: Store) -> None:
        self._s = store

    async def lock_additions(self, user_id: UserId) -> None:
        return None

    async def find_duplicate(self, user_id: UserId, fingerprint: str) -> int | None:
        for number in sorted(n for (owner, n) in self._s.facts if owner == user_id):
            if self._s.hashes[(user_id, number)] == fingerprint:
                return number
        return None

    async def add(
        self,
        user_id: UserId,
        fact_id: FactId,
        fact: NewFact,
        now: datetime,
        number: int | None = None,
    ) -> Fact:
        counter = self._s.counters.get(user_id, 0)
        given = counter + 1 if number is None else number
        self._s.counters[user_id] = max(counter, given)
        key = (user_id, given)
        added = Fact(
            fact_id,
            given,
            fact.kind,
            fact.text,
            fact.confirmed,
            now,
            now,
            fact.source,
            fact.job_number,
        )
        self._s.facts[key] = added
        self._s.hashes[key] = fact.fingerprint
        return added

    async def all(self, user_id: UserId) -> list[Fact]:
        mine = [fact for (owner, _), fact in self._s.facts.items() if owner == user_id]
        return sorted(mine, key=lambda fact: fact.number)

    async def get(self, user_id: UserId, number: int) -> Fact | None:
        return self._s.facts.get((user_id, number))

    async def replace(
        self, user_id: UserId, number: int, fact: NewFact, now: datetime
    ) -> Fact:
        key = (user_id, number)
        changed = replace(
            self._s.facts[key],
            kind=fact.kind,
            text=fact.text,
            confirmed=False,
            updated_at=now,
        )
        self._s.facts[key] = changed
        self._s.hashes[key] = fact.fingerprint
        return changed

    async def delete(self, user_id: UserId, number: int) -> None:
        self._s.facts.pop((user_id, number), None)
        self._s.hashes.pop((user_id, number), None)

    async def confirm(
        self, user_id: UserId, numbers: Collection[int], now: datetime
    ) -> None:
        for number in numbers:
            fact = self._s.facts.get((user_id, number))
            if fact is not None:
                self._s.facts[(user_id, number)] = replace(
                    fact, confirmed=True, updated_at=now
                )


class InMemoryOriginalCvs:
    def __init__(self, store: Store) -> None:
        self._s = store

    async def get(self, user_id: UserId) -> OriginalCv | None:
        return self._s.cvs.get(user_id)

    async def save(self, user_id: UserId, cv: NewOriginalCv, now: datetime) -> None:
        self._s.cvs[user_id] = OriginalCv(cv.text, cv.file_name, now)


class InMemoryFactUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(self, store: Store) -> None:
        self._store = store
        self._staged: Store | None = None

    def _open(self) -> Store:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged

    @property
    def facts(self) -> InMemoryFacts:
        return InMemoryFacts(self._open())

    @property
    def original_cvs(self) -> InMemoryOriginalCvs:
        return InMemoryOriginalCvs(self._open())

    async def __aenter__(self) -> Self:
        self._staged = self._store.copy()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        staged = self._open()
        self._store.facts, self._store.hashes = staged.facts, staged.hashes
        self._store.counters, self._store.cvs = staged.counters, staged.cvs
