"""In-memory адаптери onboarding для core-тестів: підказки й unit of work, що збирає сховища
інших контекстів (профіль, OAuth, оригінал CV, фото, пошта) — кроки рахуються з них."""

from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self

from domain.identity.ids import UserId
from domain.onboarding.steps import TipState
from domain.profile.profile import Profile
from tests.support.facts import InMemoryOriginalCvs
from tests.support.facts import Store as FactStore
from tests.support.mail import InMemoryMailInboxes, MailStore
from tests.support.oauth import InMemoryGrants, OAuthStore
from tests.support.photos import InMemoryPhotos
from tests.support.photos import Store as PhotoStore
from tests.support.profile import InMemoryProfiles


@dataclass
class OnboardingWorld:
    """Сховища всіх контекстів, з яких рахується онбординг."""

    profiles: dict[UserId, Profile] = field(default_factory=dict)
    profiles_saved_at: dict[UserId, datetime] = field(default_factory=dict)
    oauth: OAuthStore = field(default_factory=OAuthStore)
    facts: FactStore = field(default_factory=FactStore.empty)
    photos: PhotoStore = field(default_factory=PhotoStore)
    mail: MailStore = field(default_factory=MailStore)
    tips: dict[tuple[UserId, str], TipState] = field(default_factory=dict)


class InMemoryTips:
    def __init__(self, rows: dict[tuple[UserId, str], TipState]) -> None:
        self._rows = rows

    async def all(self, user_id: UserId) -> list[TipState]:
        return [tip for (owner, _), tip in self._rows.items() if owner == user_id]

    async def mark_seen(self, user_id: UserId, key: str, now: datetime) -> None:
        self._rows.setdefault((user_id, key), TipState(key, now))

    async def dismiss(self, user_id: UserId, key: str, now: datetime) -> None:
        known = self._rows.get((user_id, key))
        if known is None:
            self._rows[(user_id, key)] = TipState(key, now, now)
        elif known.dismissed_at is None:
            self._rows[(user_id, key)] = TipState(key, known.seen_at, now)


class InMemoryOnboardingUnitOfWork:
    """Читає й пише одразу в сховища світу; підказки видно лише після `commit()`."""

    def __init__(self, world: OnboardingWorld) -> None:
        self._world = world
        self._staged: dict[tuple[UserId, str], TipState] | None = None

    def _tips(self) -> dict[tuple[UserId, str], TipState]:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged

    @property
    def profiles(self) -> InMemoryProfiles:
        return InMemoryProfiles(self._world.profiles, self._world.profiles_saved_at)

    @property
    def grants(self) -> InMemoryGrants:
        return InMemoryGrants(self._world.oauth)

    @property
    def original_cvs(self) -> InMemoryOriginalCvs:
        return InMemoryOriginalCvs(self._world.facts)

    @property
    def photos(self) -> InMemoryPhotos:
        return InMemoryPhotos(self._world.photos)

    @property
    def mail_inboxes(self) -> InMemoryMailInboxes:
        return InMemoryMailInboxes(self._world.mail)

    @property
    def onboarding_tips(self) -> InMemoryTips:
        return InMemoryTips(self._tips())

    async def __aenter__(self) -> Self:
        self._staged = dict(self._world.tips)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        self._world.tips = self._tips()
