"""Порти контексту onboarding: підказки, які користувач бачив чи сховав, і unit of work, що
збирає все, за чим рахуються кроки (профіль, OAuth-гранти, оригінал CV, фото, пошта)."""

from datetime import datetime
from typing import Protocol

from application.ports.facts import OriginalCvRepository
from application.ports.mail import MailInboxRepository
from application.ports.oauth import Grants
from application.ports.photos import PhotoRepository
from application.ports.profile import ProfileRepository
from application.ports.unit_of_work import UnitOfWork
from domain.identity.ids import UserId
from domain.onboarding.steps import TipState


class OnboardingTips(Protocol):
    async def all(self, user_id: UserId) -> list[TipState]:
        """Підказки, які користувач бачив (рядок є лише в таких)."""
        ...

    async def mark_seen(self, user_id: UserId, key: str, now: datetime) -> None:
        """Повтор нічого не міняє: лишається час першого разу."""
        ...

    async def dismiss(self, user_id: UserId, key: str, now: datetime) -> None:
        """Ховає (і вважає баченою, якщо ще ні). Повтор нічого не міняє."""
        ...


class OnboardingUnitOfWork(UnitOfWork, Protocol):
    @property
    def profiles(self) -> ProfileRepository: ...

    @property
    def grants(self) -> Grants: ...

    @property
    def original_cvs(self) -> OriginalCvRepository: ...

    @property
    def photos(self) -> PhotoRepository: ...

    @property
    def mail_inboxes(self) -> MailInboxRepository: ...

    @property
    def onboarding_tips(self) -> OnboardingTips: ...
