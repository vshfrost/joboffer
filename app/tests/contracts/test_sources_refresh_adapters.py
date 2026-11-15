"""Прогін джерел зі справжніми адаптерами SmartRecruiters і Workable на записаних відповідях:
фільтр профілю доходить до адаптера й після нього; збій однієї компанії не зупиняє решту."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx2
from anyio.from_thread import BlockingPortal

from application.sources.refresh import SourceRunUseCases
from domain.identity.ids import UserId
from domain.profile.profile import Profile
from domain.sources.failure import FailureReason
from domain.sources.ids import SourceId
from domain.sources.kinds import Platform
from domain.sources.run import SourceRun, Subscription
from infrastructure.sources import build_sources
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.source_runs import InMemorySourceRunUnitOfWork, SourceRunStore
from tests.support.sources_net import Routed, ok

FIXTURES = Path(__file__).parent / "sources_fixtures"
USER = UserId(UUID(int=201))
NOW = datetime(2026, 11, 15, 8, 30, tzinfo=UTC)


class Refresh:
    def __init__(self, route: Routed) -> None:
        self.store = SourceRunStore()
        self.net = route
        self.ids = SequentialIds(900)
        self.use_cases = SourceRunUseCases(
            lambda: InMemorySourceRunUnitOfWork(self.store),
            build_sources(route.fetcher()),
            FakeClock(NOW),
            self.ids,
        )

    def subscribe(self, platform: Platform, slug: str, name: str) -> Subscription:
        sub = Subscription(SourceId(self.ids.new()), USER, platform, slug, name)
        self.store.subscriptions[sub.id] = (sub, True)
        return sub

    def exclude(self, *words: str) -> None:
        profile = Profile()
        rules = replace(profile.rules, title_exclude=words)
        self.store.profiles[USER] = replace(profile, rules=rules)

    def run_of(self, sub: Subscription) -> SourceRun:
        return self.store.runs[sub.id]


def smartrecruiters_net() -> Routed:
    pages = {"0": "smartrecruiters_list_1.json", "2": "smartrecruiters_list_2.json"}

    def route(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/postings"):
            return ok((FIXTURES / pages[request.url.params["offset"]]).read_bytes())
        name = f"smartrecruiters_detail_{request.url.path.rsplit('/', 1)[1]}.json"
        return ok((FIXTURES / name).read_bytes())

    return Routed(route)


def test_smartrecruiters_postings_the_profile_would_drop_by_title_cost_no_detail_request(
    portal: BlockingPortal,
) -> None:
    refresh = Refresh(smartrecruiters_net())
    sub = refresh.subscribe(Platform.SMARTRECRUITERS, "lumenfreight", "Lumen Freight")
    refresh.exclude("junior")

    portal.call(refresh.use_cases.refresh_sources)

    asked = [r.url.path.rsplit("/", 1)[1] for r in refresh.net.requests]
    assert "744000900000002" not in asked
    assert asked.count("744000900000001") == 1
    run = refresh.run_of(sub)
    assert run.error is None
    assert (run.summary.found, run.summary.imported, run.summary.filtered) == (2, 2, 0)
    assert len(refresh.store.jobs.jobs) == 2


def test_workable_postings_go_through_profile_filters_and_dedup(
    portal: BlockingPortal,
) -> None:
    refresh = Refresh(Routed(lambda _: ok((FIXTURES / "workable.json").read_bytes())))
    first = refresh.subscribe(Platform.WORKABLE, "brightharbor", "Brightharbor")
    refresh.exclude("data")
    portal.call(refresh.use_cases.refresh_sources)
    portal.call(refresh.use_cases.refresh_sources)

    run = refresh.run_of(first)
    assert (run.summary.found, run.summary.imported, run.summary.filtered) == (2, 0, 1)
    assert run.summary.duplicate == 1
    assert len(refresh.store.jobs.jobs) == 1


def test_workable_rate_limit_fails_only_that_company_and_the_run_goes_on(
    portal: BlockingPortal,
) -> None:
    def route(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/slow"):
            return httpx2.Response(429)
        return ok((FIXTURES / "workable.json").read_bytes())

    refresh = Refresh(Routed(route))
    slow = refresh.subscribe(Platform.WORKABLE, "slow", "Slow")
    fine = refresh.subscribe(Platform.WORKABLE, "brightharbor", "Brightharbor")

    report = portal.call(refresh.use_cases.refresh_sources)

    assert report.targets == 2
    assert refresh.run_of(slow).error is FailureReason.RATE_LIMITED
    assert refresh.run_of(fine).error is None
    assert refresh.run_of(fine).summary.imported == 2
    assert len([r for r in refresh.net.requests if r.url.path.endswith("/slow")]) == 2


def test_a_workable_account_with_no_vacancies_is_a_successful_empty_run(
    portal: BlockingPortal,
) -> None:
    refresh = Refresh(
        Routed(lambda _: ok((FIXTURES / "workable_empty.json").read_bytes()))
    )
    sleeping = refresh.subscribe(Platform.WORKABLE, "quietdock", "Quietdock")

    portal.call(refresh.use_cases.refresh_sources)

    run = refresh.run_of(sleeping)
    assert run.error is None
    assert run.summary.found == 0


def test_smartrecruiters_unknown_company_is_not_found_in_its_state(
    portal: BlockingPortal,
) -> None:
    refresh = Refresh(
        Routed(lambda _: ok((FIXTURES / "smartrecruiters_empty.json").read_bytes()))
    )
    nope = refresh.subscribe(Platform.SMARTRECRUITERS, "nope", "Nope")

    portal.call(refresh.use_cases.refresh_sources)

    assert refresh.run_of(nope).error is FailureReason.NOT_FOUND
