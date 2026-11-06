"""Тріаж за правилами (cron без LLM): хто кандидат, застарілий тріаж, `agent` недоторканний,
транзакція на користувача, ліміт прогону, лок, звіт проти аналізів."""

from dataclasses import replace
from datetime import timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.triage.auto import (
    MAX_PER_USER,
    AutoTriageReport,
    AutoTriageUseCases,
    ComparisonReport,
    PendingJob,
)
from domain.analysis.analysis import Analysis, JobAnalysis
from domain.applications.application import (
    Application,
    ApplicationChannel,
    ApplicationStatus,
)
from domain.facts.fact import Fact, FactKind
from domain.facts.ids import FactId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.profile.profile import Profile
from domain.profile.rules import Rules
from domain.profile.target import Target
from domain.triage import scoring
from domain.triage.scoring import context_digest, inputs_hash
from domain.triage.triage import Triage, TriageSource, TriageVerdict
from tests.support.clock import FakeClock
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store
from tests.support.triage import AutoRun, InMemoryAutoTriageUnitOfWork

# Три підкріплені факти вимоги: 40 + базові 30 = 70, analyse.
GOOD = "Requirements:\nPython\nDocker\nKafka"
BARE = "Great job."
FACTS = ["Python", "Docker", "Kafka"]
ALICE = UserId(SequentialIds(9001).new())
BOB = UserId(SequentialIds(9002).new())


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.store = Store.empty()
        self.profiles: dict[UserId, Profile] = {}
        self.facts = FactStore.empty()
        self.run_state = AutoRun()
        self.auto = AutoTriageUseCases(
            lambda: InMemoryAutoTriageUnitOfWork(
                self.store, self.profiles, self.facts, self.run_state
            ),
            clock,
            ids,
        )

    def seed(
        self,
        user: UserId,
        text: str | None = GOOD,
        title: str = "Engineer",
        location: str | None = None,
    ) -> int:
        """Вакансія користувача; кожна на хвилину новіша за попередню."""
        self.clock.advance(timedelta(minutes=1))

        async def run() -> int:
            async with InMemoryJobUnitOfWork(self.store) as uow:
                number = await uow.jobs.add(
                    user,
                    JobId(self.ids.new()),
                    NewJob(text=text, title=title, company="Acme", location=location),
                    self.clock.now(),
                )
                await uow.commit()
                return number

        return self.portal.call(run)

    def confirm(self, user: UserId, text: str, confirmed: bool = True) -> None:
        number = 1 + sum(1 for owner, _ in self.facts.facts if owner == user)
        self.facts.facts[(user, number)] = Fact(
            FactId(self.ids.new()),
            number,
            FactKind.SKILL,
            text,
            confirmed,
            self.clock.now(),
            self.clock.now(),
        )

    def agent_triage(self, user: UserId, number: int, score: int = 99) -> Triage:
        saved = Triage(
            number, score, TriageVerdict.ANALYSE, "Claude: add", self.clock.now()
        )
        self.store.triage[(user, number)] = saved
        return saved

    def analyse(self, user: UserId, number: int, score: int) -> None:
        self.store.analyses[(user, number)] = Analysis(
            number, JobAnalysis(score=score, summary="S."), (), self.clock.now()
        )

    def triaged(self, user: UserId, number: int) -> Triage | None:
        return self.store.triage.get((user, number))

    def run(self) -> AutoTriageReport:
        return self.portal.call(self.auto.run)

    def report(self) -> ComparisonReport:
        return self.portal.call(self.auto.report)


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def test_a_new_job_is_triaged_by_the_rules_with_its_inputs_hash(world: World) -> None:
    for fact in FACTS:
        world.confirm(ALICE, fact)
    number = world.seed(ALICE)
    world.clock.advance(timedelta(hours=1))

    report = world.run()

    assert world.triaged(ALICE, number) == Triage(
        number,
        70,
        TriageVerdict.ANALYSE,
        "Підходить: підкріплено 3 з 3 обов'язкових вимог.",
        world.clock.now(),
        TriageSource.RULES,
    )
    job = world.store.jobs[(ALICE, number)]
    context = context_digest(Profile(), FACTS)
    assert world.store.rules_hashes[(ALICE, number)] == inputs_hash(context, job)
    assert (report.locked, report.users, report.triaged, report.failures) == (
        False,
        1,
        1,
        [],
    )
    assert dict(report.verdicts) == {TriageVerdict.ANALYSE: 1}


def test_only_confirmed_facts_back_a_requirement(world: World) -> None:
    world.confirm(ALICE, "Python")
    world.confirm(ALICE, "Docker", confirmed=False)
    number = world.seed(ALICE, "Requirements:\nPython\nDocker")

    world.run()

    triage = world.triaged(ALICE, number)
    assert triage is not None
    assert (triage.score, triage.reason) == (
        50,
        "Невпевнено: у тексті мало вимог (розпізнано 2);"
        " підкріплено 1 з 2 обов'язкових вимог; бракує Docker.",
    )


def test_each_user_is_triaged_by_their_own_profile_and_facts(world: World) -> None:
    world.confirm(ALICE, "Python")
    world.confirm(BOB, "Docker")
    mine = world.seed(ALICE, "Requirements:\nPython")
    theirs = world.seed(BOB, "Requirements:\nPython")

    report = world.run()

    first, second = world.triaged(ALICE, mine), world.triaged(BOB, theirs)
    assert first is not None
    assert second is not None
    assert (first.score, second.score, report.users) == (70, 30, 2)


def test_a_second_run_with_nothing_changed_triages_nothing(world: World) -> None:
    number = world.seed(ALICE)
    world.run()
    first = world.triaged(ALICE, number)
    world.clock.advance(timedelta(days=1))

    report = world.run()

    assert report.triaged == 0
    assert world.triaged(ALICE, number) == first


def test_a_changed_profile_triages_the_job_again(world: World) -> None:
    number = world.seed(ALICE, "We are a fintech.")
    world.run()
    world.profiles[ALICE] = Profile(target=Target(target_domains=("fintech",)))
    world.clock.advance(timedelta(days=1))

    report = world.run()

    assert report.triaged == 1
    triage = world.triaged(ALICE, number)
    assert triage is not None
    assert (triage.score, triage.triaged_at) == (55, world.clock.now())


def test_a_newly_confirmed_fact_triages_the_job_again(world: World) -> None:
    number = world.seed(ALICE, "Requirements:\nPython")
    world.run()
    world.confirm(ALICE, "Python")
    world.clock.advance(timedelta(days=1))

    report = world.run()

    triage = world.triaged(ALICE, number)
    assert triage is not None
    assert (report.triaged, triage.score) == (1, 70)


def test_an_unconfirmed_fact_does_not_triage_the_job_again(world: World) -> None:
    world.seed(ALICE, "Requirements:\nPython")
    world.run()
    world.confirm(ALICE, "Python", confirmed=False)

    assert world.run().triaged == 0


def test_a_changed_job_text_triages_the_job_again(world: World) -> None:
    number = world.seed(ALICE, BARE)
    world.run()
    world.store.jobs[(ALICE, number)] = replace(
        world.store.jobs[(ALICE, number)], text="Requirements:\nPython"
    )

    assert world.run().triaged == 1


def test_an_agent_triage_is_never_overwritten(world: World) -> None:
    kept = world.seed(ALICE)
    other = world.seed(ALICE)
    saved = world.agent_triage(ALICE, kept)

    report = world.run()

    assert world.triaged(ALICE, kept) == saved
    assert (ALICE, kept) not in world.store.rules_hashes
    assert world.triaged(ALICE, other) is not None
    assert report.triaged == 1


def test_a_job_that_is_not_a_candidate_is_not_triaged(world: World) -> None:
    candidate = world.seed(ALICE)
    analysed = world.seed(ALICE)
    world.analyse(ALICE, analysed, 70)
    hidden = world.seed(ALICE)
    world.store.jobs[(ALICE, hidden)] = replace(
        world.store.jobs[(ALICE, hidden)], dismissed_at=world.clock.now()
    )
    rejected = world.seed(ALICE)
    world.store.applications[(ALICE, rejected)] = Application(
        job_number=rejected,
        status=ApplicationStatus.REJECTED,
        applied_on=world.clock.now().date(),
        channel=ApplicationChannel.EMAIL,
        ats=None,
        company_domains=(),
        company_emails=(),
        status_changed_at=world.clock.now(),
    )
    world.seed(ALICE, None)

    report = world.run()

    assert [number for (_, number) in world.store.triage] == [candidate]
    assert report.triaged == 1


def test_a_run_triages_at_most_200_jobs_per_user_newest_first(world: World) -> None:
    assert MAX_PER_USER == 200
    for _ in range(205):
        world.seed(ALICE, BARE)

    first = world.run()
    done = sorted(number for (_, number) in world.store.triage)
    second = world.run()

    assert first.triaged == 200
    assert done == list(range(6, 206))
    assert second.triaged == 5
    assert len(world.store.triage) == 205


def test_a_user_without_work_is_not_processed(world: World) -> None:
    world.seed(ALICE)
    world.seed(BOB, None)

    report = world.run()

    assert (report.users, report.triaged) == (1, 1)


def test_a_run_does_nothing_while_another_run_holds_the_lock(world: World) -> None:
    world.seed(ALICE)
    world.run_state.locked = True

    report = world.run()

    assert report == AutoTriageReport(locked=True)
    assert world.store.triage == {}


@pytest.mark.parametrize("failing", [ALICE, BOB])
def test_a_failing_user_rolls_back_alone_and_the_others_are_saved(
    world: World, failing: UserId
) -> None:
    survivor = BOB if failing == ALICE else ALICE
    broken = world.seed(failing)
    saved = world.seed(survivor)
    world.run_state.failing = {failing}

    report = world.run()

    assert world.triaged(failing, broken) is None
    assert world.triaged(survivor, saved) is not None
    assert report.failures == [(failing, "RuntimeError")]
    assert (report.users, report.triaged) == (2, 1)


def test_the_report_compares_the_rules_with_the_full_analyses(world: World) -> None:
    for fact in FACTS:
        world.confirm(ALICE, fact)
    close = world.seed(ALICE, GOOD)
    agree_skip = world.seed(ALICE, BARE)
    apart = world.seed(ALICE, GOOD)
    world.analyse(ALICE, close, 80)
    world.analyse(ALICE, agree_skip, 30)
    world.analyse(ALICE, apart, 50)
    world.seed(ALICE, BARE)
    world.seed(ALICE, GOOD)
    world.agent_triage(ALICE, 5)

    report = world.report()

    assert report.users == 1
    assert report.compared == 3
    assert report.mean_gap == pytest.approx(10.0)
    assert report.mean_abs_gap == pytest.approx(50 / 3)
    assert report.agreed == 1
    assert dict(report.verdicts) == {TriageVerdict.ANALYSE: 2, TriageVerdict.MAYBE: 1}
    assert report.pending == 1
    assert dict(report.pending_verdicts) == {TriageVerdict.MAYBE: 1}


def test_the_report_writes_nothing(world: World) -> None:
    world.seed(ALICE)
    world.analyse(ALICE, world.seed(ALICE), 70)
    before = dict(world.store.triage)

    world.report()

    assert world.store.triage == before
    assert world.store.rules_hashes == {}


def test_the_report_without_analyses_is_empty(world: World) -> None:
    world.seed(ALICE)

    report = world.report()

    assert (report.compared, report.mean_gap, report.mean_abs_gap, report.agreed) == (
        0,
        0.0,
        0.0,
        0,
    )
    assert report.pending == 1


def test_the_report_lists_each_compared_job_with_its_rules_breakdown(
    world: World,
) -> None:
    world.confirm(ALICE, "Python")
    number = world.seed(ALICE, "Requirements:\nPython\nDocker")
    world.analyse(ALICE, number, 80)
    world.seed(ALICE, BARE)

    (compared,) = world.report().jobs

    assert (compared.number, compared.analysis_score) == (number, 80)
    assert compared.rules.score == 50
    assert (compared.rules.breakdown.must, compared.rules.breakdown.must_backed) == (
        20,
        1,
    )


def test_a_compared_job_says_only_whether_its_location_and_work_mode_are_known(
    world: World,
) -> None:
    cases = [
        ("Great job.", None),
        ("Great job.", "Madrid"),
        ("Remote position.", None),
        ("Great job.", "Madrid, Remote"),
    ]
    for text, location in cases:
        world.analyse(ALICE, world.seed(ALICE, text, location=location), 70)

    flags = [(c.location_known, c.mode_known) for c in world.report().jobs]

    assert flags == [(False, False), (True, False), (False, True), (True, True)]


def test_a_changed_rules_version_triages_a_rules_job_again(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    number = world.seed(ALICE, BARE)
    world.run()
    world.clock.advance(timedelta(days=1))
    assert world.run().triaged == 0

    monkeypatch.setattr(scoring, "RULES_VERSION", scoring.RULES_VERSION + 1)
    report = world.run()

    triage = world.triaged(ALICE, number)
    assert triage is not None
    assert report.triaged == 1
    assert triage.triaged_at == world.clock.now()


def test_a_changed_rules_version_never_touches_an_agent_triage(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    number = world.seed(ALICE, BARE)
    saved = world.agent_triage(ALICE, number)

    monkeypatch.setattr(scoring, "RULES_VERSION", scoring.RULES_VERSION + 1)
    report = world.run()

    assert report.triaged == 0
    assert world.triaged(ALICE, number) == saved


def test_the_report_lists_each_pending_job_with_its_score_and_verdict(
    world: World,
) -> None:
    for fact in FACTS:
        world.confirm(ALICE, fact)
    world.profiles[ALICE] = Profile(rules=Rules(stop_words=("blockchain",)))
    good = world.seed(ALICE, GOOD)
    bare = world.seed(ALICE, BARE)
    stopped = world.seed(ALICE, f"{GOOD}\nblockchain")
    world.analyse(ALICE, world.seed(ALICE, GOOD), 70)
    world.agent_triage(ALICE, world.seed(ALICE, GOOD))

    pending = world.report().pending_jobs

    assert sorted(pending, key=lambda item: item.number) == [
        PendingJob(good, 70, TriageVerdict.ANALYSE),
        PendingJob(bare, 50, TriageVerdict.MAYBE),
        PendingJob(stopped, 70, TriageVerdict.SKIP),
    ]


def test_the_report_without_a_queue_has_no_pending_jobs(world: World) -> None:
    assert world.report().pending_jobs == []
