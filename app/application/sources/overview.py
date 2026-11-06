"""Сторінка джерел: список з останнім прогоном, «оновити зараз» (ліміт на користувача) і вакансії,
що вже не проходять фільтр профілю. Чужих джерел і вакансій тут не видно."""

from collections.abc import Callable
from datetime import datetime

from application.contracts.actor import Actor
from application.contracts.sources import RefreshState, SourcesOverview
from application.ports.clock import Clock
from application.ports.sources import SourceOverviewUnitOfWork
from application.sources.filtered import find_filtered
from domain.sources.manage import CompanyRow, FeedRow
from domain.sources.refresh_requests import (
    MANUAL_REFRESH_WINDOW,
    RefreshLimit,
    manual_refresh,
)


class SourceOverviewUseCases:
    def __init__(
        self, unit_of_work: Callable[[], SourceOverviewUnitOfWork], clock: Clock
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def overview(self, actor: Actor) -> SourcesOverview:
        """Компанії й стрічки користувача (вимкнені теж), стан «оновити зараз» і вакансії, що
        вже не проходять фільтр."""
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            companies = await uow.source_catalog.companies(actor.user_id)
            feeds = await uow.source_catalog.feeds(actor.user_id)
            requested = await uow.source_refresh_requests.since(
                actor.user_id, now - MANUAL_REFRESH_WINDOW
            )
            filtered = await find_filtered(uow, actor.user_id)
        return SourcesOverview(
            companies, feeds, _state(requested, now, companies, feeds), filtered
        )

    async def request_refresh(self, actor: Actor) -> RefreshState:
        """Запит «оновити зараз»: рядок у черзі, прогін виконує процес прогону. Ліміт —
        `RefreshLimit`."""
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            requested = await uow.source_refresh_requests.since(
                actor.user_id, now - MANUAL_REFRESH_WINDOW
            )
            limit = manual_refresh(requested, now)
            if limit.next_at is not None:
                raise RefreshLimit(limit.next_at)
            companies = await uow.source_catalog.companies(actor.user_id)
            feeds = await uow.source_catalog.feeds(actor.user_id)
            await uow.source_refresh_requests.add(actor.user_id, now)
            await uow.commit()
        return _state([*requested, now], now, companies, feeds)


def _state(
    requested: list[datetime],
    now: datetime,
    companies: list[CompanyRow],
    feeds: list[FeedRow],
) -> RefreshState:
    limit = manual_refresh(requested, now)
    runs = [row.run for row in companies] + [row.run for row in feeds]
    ran = [run.ran_at for run in runs if run is not None]
    return RefreshState(limit.remaining, limit.next_at, max(ran, default=None))
