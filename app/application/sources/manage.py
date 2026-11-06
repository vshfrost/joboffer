"""Керування джерелами: список з останнім прогоном, додати компанію (після пробного запиту) і
стрічку, вимкнути, увімкнути, видалити. Чужих джерел тут не видно: для користувача вони не існують."""

from collections.abc import Callable

from application.contracts.actor import Actor
from application.contracts.sources import CompanyInput, FeedInput
from application.ports.ids import IdGenerator
from application.ports.job_sources import CompanyProbe
from application.ports.sources import SourceManageUnitOfWork
from domain.shared.errors import InvalidValue, NotFound
from domain.sources.failure import SourceError
from domain.sources.ids import SourceId
from domain.sources.manage import (
    Company,
    CompanyRow,
    Feed,
    FeedRow,
    SourceList,
    company_exists,
    feed_exists,
    parse_company,
    parse_feed,
    probe_failure,
)


class SourceManageUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], SourceManageUnitOfWork],
        probe: CompanyProbe,
        ids: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._probe = probe
        self._ids = ids

    async def list_sources(self, actor: Actor) -> SourceList:
        """Компанії й стрічки користувача, вимкнені теж; `run` — останній прогін або `None`."""
        async with self._unit_of_work() as uow:
            catalog = uow.source_catalog
            return SourceList(
                await catalog.companies(actor.user_id),
                await catalog.feeds(actor.user_id),
            )

    async def add_company(self, actor: Actor, data: CompanyInput) -> CompanyRow:
        """Додає компанію після одного пробного запиту до її сторінки вакансій. `InvalidValue` —
        невірні значення, така компанія вже є, слагу нема на платформі або перевірити не вдалось
        (нічого не додано)."""
        new = parse_company(data.platform, data.slug, data.name)
        async with self._unit_of_work() as uow:
            if await uow.source_catalog.has_company(
                actor.user_id, new.platform, new.slug
            ):
                raise company_exists()
        try:
            await self._probe.check(new.platform, new.slug)
        except SourceError as exc:
            raise probe_failure(new.platform, new.slug, exc.reason) from exc
        company = Company(
            SourceId(self._ids.new()), new.platform, new.slug, new.name, enabled=True
        )
        async with self._unit_of_work() as uow:
            # Пробний запит міг тривати довго: за цей час таку саму могли додати ще раз.
            if not await uow.source_catalog.add_company(actor.user_id, company):
                raise company_exists()
            await uow.commit()
        return CompanyRow(company, None)

    async def add_feed(self, actor: Actor, data: FeedInput) -> FeedRow:
        """Додає RSS-стрічку. `InvalidValue` — невідоме джерело, невірні параметри чи така стрічка
        вже є."""
        new = parse_feed(data.source, data.query)
        feed = Feed(SourceId(self._ids.new()), new.source, new.query, enabled=True)
        async with self._unit_of_work() as uow:
            if not await uow.source_catalog.add_feed(actor.user_id, feed):
                raise feed_exists()
            await uow.commit()
        return FeedRow(feed, None)

    async def set_company_enabled(
        self, actor: Actor, source_id: str, enabled: bool
    ) -> CompanyRow:
        """`NotFound` — компанії нема, вона чужа або це не її id."""
        identified = _identify(source_id)
        async with self._unit_of_work() as uow:
            row = await uow.source_catalog.set_company_enabled(
                actor.user_id, identified, enabled
            )
            if row is None:
                raise NotFound("Компанію не знайдено.")
            await uow.commit()
            return row

    async def set_feed_enabled(
        self, actor: Actor, source_id: str, enabled: bool
    ) -> FeedRow:
        """`NotFound` — стрічки нема, вона чужа або це не її id."""
        identified = _identify(source_id)
        async with self._unit_of_work() as uow:
            row = await uow.source_catalog.set_feed_enabled(
                actor.user_id, identified, enabled
            )
            if row is None:
                raise NotFound("Стрічку не знайдено.")
            await uow.commit()
            return row

    async def remove_company(self, actor: Actor, source_id: str) -> None:
        """Прибирає компанію й стан її прогону; імпортовані вакансії лишаються."""
        identified = _identify(source_id)
        async with self._unit_of_work() as uow:
            if not await uow.source_catalog.delete_company(actor.user_id, identified):
                raise NotFound("Компанію не знайдено.")
            await uow.commit()

    async def remove_feed(self, actor: Actor, source_id: str) -> None:
        """Прибирає стрічку й стан її прогону; імпортовані вакансії лишаються."""
        identified = _identify(source_id)
        async with self._unit_of_work() as uow:
            if not await uow.source_catalog.delete_feed(actor.user_id, identified):
                raise NotFound("Стрічку не знайдено.")
            await uow.commit()


def _identify(raw: str) -> SourceId:
    """id з шляху запиту; те, що не може бути id джерела, — таке саме «не знайдено», як нестворене."""
    try:
        return SourceId.parse(raw)
    except InvalidValue:
        raise NotFound("Джерело не знайдено.") from None
