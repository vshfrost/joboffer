"""Прогін джерел на Postgres (AsyncSession одного UoW)."""

from datetime import datetime
from uuid import UUID

import psycopg.errors
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.sources import SourceGone
from domain.identity.ids import UserId
from domain.sources.failure import FailureReason
from domain.sources.ids import SourceId
from domain.sources.importing import ImportSummary
from domain.sources.kinds import FeedSource, Platform
from domain.sources.manage import Company, CompanyRow, Feed, FeedRow
from domain.sources.run import SourceRun, Subscription
from infrastructure.db.sources.tables import (
    SourceCompanyRow,
    SourceCompanyRunRow,
    SourceFeedRow,
    SourceFeedRunRow,
    SourceRefreshRequestRow,
)

# Ключ pg advisory lock прогону джерел: один прогін на базу (не той, що в синку пошти).
RUN_LOCK_KEY = 0x736F757263657331  # «sources1» в ASCII


class PostgresSourceRuns:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self) -> bool:
        # Транзакційне: відпускається з commit / rollback, навіть якщо процес упав.
        locked: bool = (
            await self._session.execute(
                select(func.pg_try_advisory_xact_lock(RUN_LOCK_KEY))
            )
        ).scalar_one()
        return locked

    async def enabled(self) -> list[Subscription]:
        companies = await self._session.execute(
            select(SourceCompanyRow)
            .where(SourceCompanyRow.enabled)
            .order_by(SourceCompanyRow.created_at, SourceCompanyRow.id)
        )
        feeds = await self._session.execute(
            select(SourceFeedRow)
            .where(SourceFeedRow.enabled)
            .order_by(SourceFeedRow.created_at, SourceFeedRow.id)
        )
        return [
            Subscription(
                SourceId(company.id),
                UserId(company.user_id),
                Platform(company.platform),
                company.slug,
                company.name,
            )
            for company in companies.scalars()
        ] + [
            Subscription(
                SourceId(feed.id),
                UserId(feed.user_id),
                FeedSource(feed.source),
                feed.query,
            )
            for feed in feeds.scalars()
        ]

    async def save(self, subscription: Subscription, run: SourceRun) -> None:
        values = {
            "ran_at": run.ran_at,
            "found": run.summary.found,
            "imported": run.summary.imported,
            "filtered": run.summary.filtered,
            "duplicate": run.summary.duplicate,
            "completed": run.summary.completed,
            "error": run.error.value if run.error else None,
        }
        try:
            if isinstance(subscription.kind, Platform):
                await self._session.execute(
                    pg_insert(SourceCompanyRunRow)
                    .values(company_id=subscription.id.value, **values)
                    .on_conflict_do_update(
                        index_elements=[SourceCompanyRunRow.company_id], set_=values
                    )
                )
            else:
                await self._session.execute(
                    pg_insert(SourceFeedRunRow)
                    .values(feed_id=subscription.id.value, **values)
                    .on_conflict_do_update(
                        index_elements=[SourceFeedRunRow.feed_id], set_=values
                    )
                )
        except IntegrityError as exc:
            # Зовнішній ключ: джерело видалили, поки його читали. Транзакція зламана — відкочується.
            if isinstance(exc.orig, psycopg.errors.ForeignKeyViolation):
                raise SourceGone from exc
            raise


def _run_of(
    row: SourceCompanyRunRow | SourceFeedRunRow | None,
) -> SourceRun | None:
    if row is None:
        return None
    return SourceRun(
        row.ran_at,
        ImportSummary(
            found=row.found,
            imported=row.imported,
            filtered=row.filtered,
            duplicate=row.duplicate,
            completed=row.completed,
        ),
        None if row.error is None else FailureReason(row.error),
    )


def _company_row(
    company: SourceCompanyRow, run: SourceCompanyRunRow | None
) -> CompanyRow:
    return CompanyRow(
        Company(
            SourceId(company.id),
            Platform(company.platform),
            company.slug,
            company.name,
            company.enabled,
        ),
        _run_of(run),
    )


def _feed_row(feed: SourceFeedRow, run: SourceFeedRunRow | None) -> FeedRow:
    return FeedRow(
        Feed(SourceId(feed.id), FeedSource(feed.source), feed.query, feed.enabled),
        _run_of(run),
    )


class PostgresSourceCatalog:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def companies(self, user_id: UserId) -> list[CompanyRow]:
        found = await self._session.execute(
            select(SourceCompanyRow, SourceCompanyRunRow)
            .outerjoin(
                SourceCompanyRunRow,
                SourceCompanyRunRow.company_id == SourceCompanyRow.id,
            )
            .where(SourceCompanyRow.user_id == user_id.value)
            .order_by(func.lower(SourceCompanyRow.name), SourceCompanyRow.slug)
        )
        return [_company_row(company, run) for company, run in found.all()]

    async def has_company(self, user_id: UserId, platform: Platform, slug: str) -> bool:
        found = await self._session.execute(
            select(SourceCompanyRow.id).where(
                SourceCompanyRow.user_id == user_id.value,
                SourceCompanyRow.platform == platform.value,
                SourceCompanyRow.slug == slug,
            )
        )
        return found.first() is not None

    async def add_company(self, user_id: UserId, company: Company) -> bool:
        added = await self._session.execute(
            pg_insert(SourceCompanyRow)
            .values(
                id=company.id.value,
                user_id=user_id.value,
                platform=company.platform.value,
                slug=company.slug,
                name=company.name,
                enabled=company.enabled,
            )
            .on_conflict_do_nothing()
            .returning(SourceCompanyRow.id)
        )
        return added.first() is not None

    async def set_company_enabled(
        self, user_id: UserId, source_id: SourceId, enabled: bool
    ) -> CompanyRow | None:
        changed = await self._session.execute(
            update(SourceCompanyRow)
            .where(
                SourceCompanyRow.id == source_id.value,
                SourceCompanyRow.user_id == user_id.value,
            )
            .values(enabled=enabled)
            .returning(SourceCompanyRow.id)
        )
        if changed.first() is None:
            return None
        return await self._company(source_id.value)

    async def delete_company(self, user_id: UserId, source_id: SourceId) -> bool:
        # Стан прогону зникає каскадом (FK ON DELETE CASCADE); вакансії від джерела не залежать.
        deleted = await self._session.execute(
            delete(SourceCompanyRow)
            .where(
                SourceCompanyRow.id == source_id.value,
                SourceCompanyRow.user_id == user_id.value,
            )
            .returning(SourceCompanyRow.id)
        )
        return deleted.first() is not None

    async def _company(self, company_id: UUID) -> CompanyRow:
        found = await self._session.execute(
            select(SourceCompanyRow, SourceCompanyRunRow)
            .outerjoin(
                SourceCompanyRunRow,
                SourceCompanyRunRow.company_id == SourceCompanyRow.id,
            )
            .where(SourceCompanyRow.id == company_id)
        )
        company, run = found.one()
        return _company_row(company, run)

    async def feeds(self, user_id: UserId) -> list[FeedRow]:
        found = await self._session.execute(
            select(SourceFeedRow, SourceFeedRunRow)
            .outerjoin(SourceFeedRunRow, SourceFeedRunRow.feed_id == SourceFeedRow.id)
            .where(SourceFeedRow.user_id == user_id.value)
            .order_by(SourceFeedRow.source, SourceFeedRow.query)
        )
        return [_feed_row(feed, run) for feed, run in found.all()]

    async def add_feed(self, user_id: UserId, feed: Feed) -> bool:
        added = await self._session.execute(
            pg_insert(SourceFeedRow)
            .values(
                id=feed.id.value,
                user_id=user_id.value,
                source=feed.source.value,
                query=feed.query,
                enabled=feed.enabled,
            )
            .on_conflict_do_nothing()
            .returning(SourceFeedRow.id)
        )
        return added.first() is not None

    async def set_feed_enabled(
        self, user_id: UserId, source_id: SourceId, enabled: bool
    ) -> FeedRow | None:
        changed = await self._session.execute(
            update(SourceFeedRow)
            .where(
                SourceFeedRow.id == source_id.value,
                SourceFeedRow.user_id == user_id.value,
            )
            .values(enabled=enabled)
            .returning(SourceFeedRow.id)
        )
        if changed.first() is None:
            return None
        return await self._feed(source_id.value)

    async def _feed(self, feed_id: UUID) -> FeedRow:
        found = await self._session.execute(
            select(SourceFeedRow, SourceFeedRunRow)
            .outerjoin(SourceFeedRunRow, SourceFeedRunRow.feed_id == SourceFeedRow.id)
            .where(SourceFeedRow.id == feed_id)
        )
        feed, run = found.one()
        return _feed_row(feed, run)

    async def delete_feed(self, user_id: UserId, source_id: SourceId) -> bool:
        deleted = await self._session.execute(
            delete(SourceFeedRow)
            .where(
                SourceFeedRow.id == source_id.value,
                SourceFeedRow.user_id == user_id.value,
            )
            .returning(SourceFeedRow.id)
        )
        return deleted.first() is not None


class PostgresSourceRefreshRequests:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def since(self, user_id: UserId, moment: datetime) -> list[datetime]:
        found = await self._session.execute(
            select(SourceRefreshRequestRow.requested_at).where(
                SourceRefreshRequestRow.user_id == user_id.value,
                SourceRefreshRequestRow.requested_at > moment,
            )
        )
        return list(found.scalars())

    async def add(self, user_id: UserId, requested_at: datetime) -> None:
        self._session.add(
            SourceRefreshRequestRow(user_id=user_id.value, requested_at=requested_at)
        )

    async def mark_handled(self, handled_at: datetime) -> int:
        done = await self._session.execute(
            update(SourceRefreshRequestRow)
            .where(SourceRefreshRequestRow.handled_at.is_(None))
            .values(handled_at=handled_at)
        )
        return int(done.rowcount)  # type: ignore[attr-defined]
