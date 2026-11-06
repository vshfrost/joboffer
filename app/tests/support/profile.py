"""In-memory адаптер profile для core-тестів: та сама семантика, що в Postgres (commit, порожній профіль)."""

from datetime import datetime
from types import TracebackType
from typing import Self

from domain.identity.ids import UserId
from domain.profile.profile import Profile, ProfileSection


class InMemoryProfiles:
    def __init__(
        self,
        rows: dict[UserId, Profile],
        saved_at: dict[UserId, datetime],
        inputs_changed: dict[UserId, datetime] | None = None,
    ) -> None:
        self._rows = rows
        self._saved_at = saved_at
        self._inputs_changed = {} if inputs_changed is None else inputs_changed

    async def get(self, user_id: UserId) -> Profile:
        return self._rows.get(user_id, Profile())

    async def save_section(
        self, user_id: UserId, section: ProfileSection, now: datetime
    ) -> None:
        self._rows[user_id] = (await self.get(user_id)).with_section(section)
        self._saved_at[user_id] = now

    async def replace(self, user_id: UserId, profile: Profile, now: datetime) -> None:
        self._rows[user_id] = profile
        self._saved_at[user_id] = now

    async def analysis_inputs_changed_at(self, user_id: UserId) -> datetime | None:
        return self._inputs_changed.get(user_id)

    async def mark_analysis_inputs_changed(
        self, user_id: UserId, now: datetime
    ) -> None:
        self._inputs_changed[user_id] = now


class InMemoryProfileUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(
        self,
        store: dict[UserId, Profile],
        saved_at: dict[UserId, datetime],
        inputs_changed: dict[UserId, datetime] | None = None,
    ) -> None:
        self._store = store
        self._saved_at_store = saved_at
        self._inputs_store: dict[UserId, datetime] = (
            {} if inputs_changed is None else inputs_changed
        )
        self._staged: dict[UserId, Profile] | None = None
        self._staged_at: dict[UserId, datetime] = {}
        self._staged_inputs: dict[UserId, datetime] = {}

    @property
    def profiles(self) -> InMemoryProfiles:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemoryProfiles(self._staged, self._staged_at, self._staged_inputs)

    async def __aenter__(self) -> Self:
        self._staged = dict(self._store)
        self._staged_at = dict(self._saved_at_store)
        self._staged_inputs = dict(self._inputs_store)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        self._store.clear()
        self._store.update(self._staged)
        self._saved_at_store.clear()
        self._saved_at_store.update(self._staged_at)
        self._inputs_store.clear()
        self._inputs_store.update(self._staged_inputs)
