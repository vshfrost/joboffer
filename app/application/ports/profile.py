"""Порти контексту profile: репозиторій профілів і unit of work, що його відкриває."""

from datetime import datetime
from typing import Protocol

from application.ports.unit_of_work import UnitOfWork
from domain.identity.ids import UserId
from domain.profile.profile import Profile, ProfileSection


class ProfileRepository(Protocol):
    async def get(self, user_id: UserId) -> Profile:
        """Профіль користувача; рядка ще нема — порожній профіль."""
        ...

    async def save_section(
        self, user_id: UserId, section: ProfileSection, now: datetime
    ) -> None:
        """Змінює лише поля цього розділу; решта профілю лишається як є."""
        ...

    async def replace(self, user_id: UserId, profile: Profile, now: datetime) -> None:
        """Замінює профіль цілком."""
        ...

    async def analysis_inputs_changed_at(self, user_id: UserId) -> datetime | None:
        """Коли востаннє змінилась ціль, локації чи правила; None — ще не змінювались."""
        ...

    async def mark_analysis_inputs_changed(
        self, user_id: UserId, now: datetime
    ) -> None:
        """Фіксує зміну цілі, локацій чи правил (профіль уже збережено)."""
        ...


class ProfileUnitOfWork(UnitOfWork, Protocol):
    @property
    def profiles(self) -> ProfileRepository: ...
