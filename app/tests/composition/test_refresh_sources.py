"""Запуск прогону джерел: один прохід, аудит SOURCES_AUDIT без вмісту вакансій, код виходу,
складання адаптерів у composition root."""

import logging
from datetime import UTC, datetime
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal

from application.ports.job_sources import JobSource
from application.sources.refresh import SourceRunUseCases
from bootstrap import refresh_sources
from domain.identity.ids import UserId
from domain.sources.failure import FailureReason
from domain.sources.ids import SourceId
from domain.sources.kinds import FeedSource, Platform, SourceKind
from domain.sources.posting import Posting
from domain.sources.run import Subscription
from domain.sources.target import SourceTarget
from infrastructure.sources.http import Fetcher
from tests.support.clock import FakeClock
from tests.support.core_conftest import portal
from tests.support.ids import SequentialIds
from tests.support.source_runs import (
    InMemorySourceRunUnitOfWork,
    SourceRunStore,
    registry,
)

__all__ = ["portal"]

DUMMY_URL = "postgresql+psycopg://joboffer@localhost:1/joboffer"
NOW = datetime(2026, 10, 26, 8, 30, tzinfo=UTC)
TARAS = UserId(UUID(int=101))
KATYA = UserId(UUID(int=102))


@pytest.fixture(autouse=True)
def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBOFFER_DATABASE_URL", DUMMY_URL)


@pytest.fixture
def audit_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> pytest.LogCaptureFixture:
    """Аудит-логер доступний для caplog: попередні тести (import-linter) налаштовують logging
    через dictConfig і вимикають вже створені логери."""
    for name in ("joboffer", "joboffer.sources"):
        logger = logging.getLogger(name)
        monkeypatch.setattr(logger, "disabled", False)
        monkeypatch.setattr(logger, "propagate", True)
    caplog.set_level(logging.INFO, logger="joboffer.sources")
    return caplog


def posting(title: str) -> Posting:
    return Posting(
        title=title,
        url=f"https://jobs.example/{title.replace(' ', '-')}",
        text=f"Secret body of {title}",
        company="Secret Globex",
        locations=("Secret City",),
    )


class Run:
    def __init__(self) -> None:
        self.store = SourceRunStore()
        self.reads: list[SourceTarget] = []
        self.scripts = registry([Platform.GREENHOUSE, FeedSource.DOU], self.reads)
        self.ids = SequentialIds(500)

    def subscribe(
        self, user: UserId, kind: SourceKind, ref: str, name: str = ""
    ) -> Subscription:
        sub = Subscription(SourceId(self.ids.new()), user, kind, ref, name)
        self.store.subscriptions[sub.id] = (sub, True)
        return sub

    def use_cases(self) -> SourceRunUseCases:
        sources: dict[SourceKind, JobSource] = dict(self.scripts)
        return SourceRunUseCases(
            lambda: InMemorySourceRunUnitOfWork(self.store),
            sources,
            FakeClock(NOW),
            SequentialIds(900),
        )

    def run(self, portal: BlockingPortal) -> int:
        return portal.call(refresh_sources.run_refresh, self.use_cases())


def test_run_writes_audit_lines_without_vacancy_content(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run()
    greenhouse = run.subscribe(TARAS, Platform.GREENHOUSE, "acme", "Secret Acme")
    run.subscribe(KATYA, Platform.GREENHOUSE, "acme", "Secret Acme")
    run.scripts[Platform.GREENHOUSE].postings["acme"] = [
        posting("Secret Backend Role"),
        posting("Secret Data Role"),
    ]
    feed = run.subscribe(TARAS, FeedSource.DOU, "category=Python")
    run.scripts[FeedSource.DOU].failures["category=Python"] = FailureReason.TIMEOUT

    code = run.run(portal)

    assert code == 0
    assert (
        f"SOURCES_AUDIT source=ats:greenhouse ref=acme user={TARAS} found=2 imported=2"
        " filtered=0 duplicate=0 completed=0 error=-" in audit_log.text
    )
    assert (
        f"SOURCES_AUDIT source=ats:greenhouse ref=acme user={KATYA} found=2 imported=2"
        " filtered=0 duplicate=0 completed=0 error=-" in audit_log.text
    )
    assert (
        f"SOURCES_AUDIT source=rss:dou ref=category=Python user={TARAS} found=0"
        " imported=0 filtered=0 duplicate=0 completed=0 error=timeout" in audit_log.text
    )
    assert "SOURCES_AUDIT run done: targets=2 sources=3 failed=1" in audit_log.text
    assert greenhouse.id in run.store.runs
    assert feed.id in run.store.runs
    for secret in ("Secret", "Backend Role", "jobs.example"):
        assert secret not in audit_log.text


def test_a_crash_while_reading_is_audited_as_invalid_without_its_text(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run()
    crashed = run.subscribe(TARAS, Platform.GREENHOUSE, "acme", "Secret Acme")
    run.scripts[Platform.GREENHOUSE].crashes["acme"] = RuntimeError(
        "Secret Backend Role: розбір упав"
    )
    feed = run.subscribe(TARAS, FeedSource.DOU, "category=Python")
    run.scripts[FeedSource.DOU].postings["category=Python"] = [posting("Secret Data")]

    aborted: Exception | None = None
    try:
        code = run.run(portal)
    except Exception as exc:
        aborted, code = exc, 1

    assert aborted is None, repr(aborted)
    assert code == 0
    assert (
        f"SOURCES_AUDIT source=ats:greenhouse ref=acme user={TARAS} found=0 imported=0"
        " filtered=0 duplicate=0 completed=0 error=invalid" in audit_log.text
    )
    assert "SOURCES_AUDIT run done: targets=2 sources=2 failed=1" in audit_log.text
    assert crashed.id in run.store.runs
    assert feed.id in run.store.runs
    for secret in ("Secret", "Backend Role", "розбір упав"):
        assert secret not in audit_log.text


def test_run_skips_while_another_run_holds_the_lock(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run()
    run.subscribe(TARAS, Platform.GREENHOUSE, "acme", "Acme")
    run.store.locked = True

    code = run.run(portal)

    assert code == 0
    assert "SOURCES_AUDIT run skipped" in audit_log.text
    assert run.reads == []
    assert run.store.runs == {}


def test_run_with_no_sources_is_done_and_exits_with_zero(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    code = Run().run(portal)

    assert code == 0
    assert "SOURCES_AUDIT run done: targets=0 sources=0 failed=0" in audit_log.text


class FakeEngine:
    disposed = False

    async def dispose(self) -> None:
        self.disposed = True


@pytest.fixture
def main_env(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Run, FakeEngine, list[Fetcher]]:
    """`main()` без мережі й бази: engine і сховище підмінені, реєстр адаптерів — сценарії."""
    run, engine, fetchers = Run(), FakeEngine(), []

    def build(fetcher: Fetcher) -> dict[SourceKind, JobSource]:
        fetchers.append(fetcher)
        return dict(run.scripts)

    monkeypatch.setattr(refresh_sources, "create_engine", lambda url: engine)
    monkeypatch.setattr(
        refresh_sources,
        "unit_of_work_factory",
        lambda _engine: lambda: InMemorySourceRunUnitOfWork(run.store),
    )
    monkeypatch.setattr(refresh_sources, "build_sources", build)
    return run, engine, fetchers


def test_main_builds_the_adapters_runs_once_and_releases_the_engine(
    main_env: tuple[Run, FakeEngine, list[Fetcher]],
) -> None:
    run, engine, fetchers = main_env
    sub = run.subscribe(TARAS, Platform.GREENHOUSE, "acme", "Acme")
    run.scripts[Platform.GREENHOUSE].postings["acme"] = [posting("Backend Role")]

    refresh_sources.main()

    assert len(fetchers) == 1
    assert sub.id in run.store.runs
    assert [(t.kind, t.ref) for t in run.reads] == [(Platform.GREENHOUSE, "acme")]
    assert engine.disposed


def test_main_does_not_fail_the_process_when_one_source_fails(
    main_env: tuple[Run, FakeEngine, list[Fetcher]],
) -> None:
    run, engine, _ = main_env
    sub = run.subscribe(TARAS, Platform.GREENHOUSE, "acme", "Acme")
    run.scripts[Platform.GREENHOUSE].failures["acme"] = FailureReason.NOT_FOUND

    refresh_sources.main()

    saved = run.store.runs.get(sub.id)
    assert saved is not None
    assert saved.error is FailureReason.NOT_FOUND
    assert engine.disposed
