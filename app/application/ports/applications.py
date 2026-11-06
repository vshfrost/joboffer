"""Порт контексту applications: репозиторій подач.

Подача скрізь — за номером вакансії в межах користувача (`job_number`); чужа й неіснуюча
не відрізняються. Одна подача на вакансію.
"""

from datetime import datetime
from typing import Protocol

from domain.applications.application import (
    Application,
    ApplicationStatus,
    NewApplication,
)
from domain.identity.ids import UserId


class ApplicationRepository(Protocol):
    async def get(self, user_id: UserId, job_number: int) -> Application | None: ...

    async def save(
        self, user_id: UserId, job_number: int, details: NewApplication, now: datetime
    ) -> Application:
        """Нова подача — зі статусом `applied` і `status_changed_at = now`; наявна — деталі
        замінено (разом з версією CV: `details.cv` None її забуває), статус і
        `status_changed_at` лишились. Вакансія має існувати."""
        ...

    async def list_all(self, user_id: UserId) -> list[Application]:
        """Усі подачі користувача за номером вакансії, з версією CV (`cv`)."""
        ...

    async def set_status(
        self,
        user_id: UserId,
        job_number: int,
        status: ApplicationStatus,
        now: datetime,
    ) -> Application:
        """Ставить статус і `status_changed_at = now`; перехід уже перевірено. Подача має бути."""
        ...
