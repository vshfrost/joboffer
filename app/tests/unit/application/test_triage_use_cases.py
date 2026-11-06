"""Use cases тріажу: бриф для Claude, збереження пачки (усе або нічого), ізоляція, список за тріажем.

Семантика і тексти помилок — як у v1 (`origin/main` `99a2007`); пачка агента — 5, кандидати — без
тріажу або з тріажем `rules` і вердиктом maybe, спільний контекст — лише в першому виклику.
"""

from datetime import date, timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.jobs import JobData, JobSearchInput, JobSummaryData
from application.contracts.profile import ProfileData, TargetData
from application.contracts.triage import (
    SavedTriageData,
    TriageBriefData,
    TriageFactData,
    TriageInput,
)
from application.jobs.use_cases import JobUseCases
from application.ports.prompts import PromptKey
from application.triage.use_cases import TriageUseCases
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
from domain.profile.target import Target
from domain.shared.errors import InvalidFields, InvalidValue
from domain.triage.brief import TextScope
from domain.triage.triage import Triage, TriageSource, TriageVerdict
from tests.support.clock import FakeClock
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store
from tests.support.triage import InMemoryTriageUnitOfWork

RULES = "Quick triage rules. Then call save_triage."


class FakePrompts:
    def get(self, key: PromptKey) -> str:
        assert key is PromptKey.TRIAGE_RULES
        return RULES


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
        self.alice = self._actor()
        self.bob = self._actor()
        self.triage = TriageUseCases(
            lambda: InMemoryTriageUnitOfWork(
                self.store, self.profiles, facts=self.facts
            ),
            clock,
            ids,
            FakePrompts(),
        )
        self.jobs = JobUseCases(lambda: InMemoryJobUnitOfWork(self.store), clock, ids)

    def _actor(self) -> Actor:
        return Actor(
            user_id=UserId(self.ids.new()),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )

    def seed(
        self,
        actor: Actor,
        text: str | None = "Senior Python engineer. Remote.",
        *,
        title: str | None = "Engineer",
        company: str | None = "Acme",
        location: str | None = None,
        source: str = "manual",
    ) -> int:
        """Вакансія з довільним станом (без тексту — з листа-алерту); кожна на хвилину новіша."""
        self.clock.advance(timedelta(minutes=1))

        async def run() -> int:
            async with InMemoryJobUnitOfWork(self.store) as uow:
                number = await uow.jobs.add(
                    actor.user_id,
                    JobId(self.ids.new()),
                    NewJob(
                        text=text,
                        title=title,
                        company=company,
                        location=location,
                        source=source,
                    ),
                    self.clock.now(),
                )
                await uow.commit()
                return number

        return self.portal.call(run)

    def apply(self, actor: Actor, number: int, status: ApplicationStatus) -> None:
        """Подача на вакансію одразу в потрібному статусі."""
        self.store.applications[(actor.user_id, number)] = Application(
            job_number=number,
            status=status,
            applied_on=date(2026, 1, 1),
            channel=ApplicationChannel.EMAIL,
            ats=None,
            company_domains=(),
            company_emails=(),
            status_changed_at=self.clock.now(),
        )

    def analyse(self, actor: Actor, number: int) -> None:
        self.store.analyses[(actor.user_id, number)] = Analysis(
            number, JobAnalysis(score=70, summary="S."), (), self.clock.now()
        )

    def confirm(
        self, actor: Actor, kind: FactKind, text: str, confirmed: bool = True
    ) -> None:
        number = 1 + sum(1 for owner, _ in self.facts.facts if owner == actor.user_id)
        self.facts.facts[(actor.user_id, number)] = Fact(
            FactId(self.ids.new()),
            number,
            kind,
            text,
            confirmed,
            self.clock.now(),
            self.clock.now(),
        )

    def rate_by_rules(
        self, actor: Actor, number: int, verdict: TriageVerdict, score: int = 50
    ) -> None:
        """Тріаж cron (`source = rules`): із відбитком вхідних даних."""
        self.store.triage[(actor.user_id, number)] = Triage(
            number, score, verdict, "Rules", self.clock.now(), TriageSource.RULES
        )
        self.store.rules_hashes[(actor.user_id, number)] = "hash"

    def prepare(
        self, actor: Actor, limit: int = 5, include_context: bool = True
    ) -> TriageBriefData:
        return self.portal.call(
            self.triage.prepare_triage, actor, limit, include_context
        )

    def save(self, actor: Actor, *items: tuple[int, int, str, str]) -> SavedTriageData:
        return self.portal.call(self.triage.save_triage, actor, self.inputs(items))

    @staticmethod
    def inputs(items: tuple[tuple[int, int, str, str], ...]) -> list[TriageInput]:
        return [
            TriageInput(job_number=number, score=score, verdict=verdict, reason=reason)
            for number, score, verdict, reason in items
        ]

    def listed(self, actor: Actor, **fields: object) -> list[JobSummaryData]:
        data = JobSearchInput(**fields)  # type: ignore[arg-type]
        return self.portal.call(self.jobs.list_jobs, actor, data)

    def numbers(self, actor: Actor, **fields: object) -> list[int]:
        return [item.job_number for item in self.listed(actor, **fields)]

    def details(self, actor: Actor, number: int) -> JobData:
        return self.portal.call(self.jobs.get_job, actor, number)


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def numbers_of(brief: TriageBriefData) -> list[int]:
    return [job.job_number for job in brief.jobs]


# --- prepare_triage ---------------------------------------------------------


def test_the_brief_lists_the_newest_jobs_first(world: World) -> None:
    first = world.seed(world.alice)
    second = world.seed(world.alice)
    third = world.seed(world.alice)
    assert numbers_of(world.prepare(world.alice)) == [third, second, first]


def test_the_brief_is_cut_to_the_limit_and_pending_counts_every_waiting_job(
    world: World,
) -> None:
    for _ in range(5):
        world.seed(world.alice)
    brief = world.prepare(world.alice, 2)
    assert (numbers_of(brief), brief.pending) == ([5, 4], 5)


def test_the_default_limit_is_a_batch_of_5(world: World) -> None:
    for _ in range(8):
        world.seed(world.alice)
    brief = world.portal.call(world.triage.prepare_triage, world.alice)
    assert (len(brief.jobs), brief.pending) == (5, 8)


@pytest.mark.parametrize("limit", [0, -1, 6, 20])
def test_a_limit_outside_1_to_5_is_rejected(world: World, limit: int) -> None:
    with pytest.raises(InvalidValue) as error:
        world.prepare(world.alice, limit)
    assert error.value.message == "Ліміт — від 1 до 5."


def test_a_candidate_carries_the_fields_the_model_needs(world: World) -> None:
    number = world.seed(
        world.alice,
        "Senior Go role",
        title="Go Engineer",
        company="Acme",
        location="Berlin",
        source="greenhouse:acme",
    )
    [job] = world.prepare(world.alice).jobs
    assert (
        job.job_number,
        job.title,
        job.company,
        job.source,
        job.location,
        job.text,
        job.text_scope,
    ) == (
        number,
        "Go Engineer",
        "Acme",
        "greenhouse:acme",
        "Berlin",
        "Senior Go role",
        TextScope.FULL,
    )


def test_a_text_without_requirement_sections_comes_whole_not_cut(
    world: World,
) -> None:
    world.seed(world.alice, "a" * 1600 + "TAIL")
    [job] = world.prepare(world.alice).jobs
    assert (job.text, job.text_scope) == ("a" * 1600 + "TAIL", TextScope.FULL)


def test_a_text_with_requirement_sections_comes_as_only_those_sections(
    world: World,
) -> None:
    world.seed(
        world.alice,
        "About us\nGreat company.\n\nRequirements:\n- Python\n- Docker\n\n"
        "Nice to have:\n- Kafka\n\nBenefits:\nFree lunch",
    )
    [job] = world.prepare(world.alice).jobs
    assert (job.text, job.text_scope) == (
        "Requirements:\n- Python\n- Docker\n\nNice to have:\n- Kafka",
        TextScope.REQUIREMENTS,
    )


def test_each_job_of_a_batch_gets_its_own_scope(world: World) -> None:
    sectioned = world.seed(world.alice, "Intro\n\nRequirements:\n- Python")
    plain = world.seed(world.alice, "Just a plain text.")
    brief = world.prepare(world.alice)
    assert [(job.job_number, job.text_scope) for job in brief.jobs] == [
        (plain, TextScope.FULL),
        (sectioned, TextScope.REQUIREMENTS),
    ]


def test_jobs_without_text_are_not_candidates(world: World) -> None:
    world.seed(world.alice, None)
    brief = world.prepare(world.alice)
    assert (numbers_of(brief), brief.pending) == ([], 0)


def test_hidden_jobs_are_not_candidates(world: World) -> None:
    hidden = world.seed(world.alice)
    kept = world.seed(world.alice)
    world.portal.call(world.jobs.dismiss_jobs, world.alice, [hidden], "не цікаво")
    brief = world.prepare(world.alice)
    assert (numbers_of(brief), brief.pending) == ([kept], 1)


def test_analysed_jobs_are_not_candidates(world: World) -> None:
    analysed = world.seed(world.alice)
    world.analyse(world.alice, analysed)
    brief = world.prepare(world.alice)
    assert (numbers_of(brief), brief.pending) == ([], 0)


@pytest.mark.parametrize(
    "status", [ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN]
)
def test_a_job_with_a_closed_application_is_not_a_candidate(
    world: World, status: ApplicationStatus
) -> None:
    closed = world.seed(world.alice)
    kept = world.seed(world.alice)
    world.apply(world.alice, closed, status)
    brief = world.prepare(world.alice)
    assert (numbers_of(brief), brief.pending) == ([kept], 1)


@pytest.mark.parametrize(
    "status",
    [
        ApplicationStatus.APPLIED,
        ApplicationStatus.REPLIED,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.OFFER,
    ],
)
def test_a_job_with_an_active_application_stays_a_candidate(
    world: World, status: ApplicationStatus
) -> None:
    active = world.seed(world.alice)
    world.apply(world.alice, active, status)
    brief = world.prepare(world.alice)
    assert (numbers_of(brief), brief.pending) == ([active], 1)


def test_jobs_triaged_by_the_agent_leave_the_brief(world: World) -> None:
    done = world.seed(world.alice)
    waiting = world.seed(world.alice)
    world.save(world.alice, (done, 80, "analyse", "Fits"))
    brief = world.prepare(world.alice)
    assert (numbers_of(brief), brief.pending) == ([waiting], 1)


def test_an_agent_triage_with_verdict_maybe_leaves_the_brief_too(
    world: World,
) -> None:
    done = world.seed(world.alice)
    world.save(world.alice, (done, 50, "maybe", "Unsure"))
    brief = world.prepare(world.alice)
    assert (brief.jobs, brief.pending) == ((), 0)


def test_a_job_the_rules_rated_maybe_stays_in_the_brief(world: World) -> None:
    unsure = world.seed(world.alice)
    world.rate_by_rules(world.alice, unsure, TriageVerdict.MAYBE)
    brief = world.prepare(world.alice)
    assert (numbers_of(brief), brief.pending) == ([unsure], 1)


@pytest.mark.parametrize("verdict", [TriageVerdict.ANALYSE, TriageVerdict.SKIP])
def test_a_job_the_rules_rated_analyse_or_skip_leaves_the_brief(
    world: World, verdict: TriageVerdict
) -> None:
    rated = world.seed(world.alice)
    world.rate_by_rules(world.alice, rated, verdict)
    brief = world.prepare(world.alice)
    assert (brief.jobs, brief.pending) == ((), 0)


def test_new_jobs_and_rules_maybe_jobs_share_one_brief_newest_first(
    world: World,
) -> None:
    unsure = world.seed(world.alice)
    settled = world.seed(world.alice)
    fresh = world.seed(world.alice)
    world.rate_by_rules(world.alice, unsure, TriageVerdict.MAYBE)
    world.rate_by_rules(world.alice, settled, TriageVerdict.SKIP)
    brief = world.prepare(world.alice)
    assert (numbers_of(brief), brief.pending) == ([fresh, unsure], 2)


def test_a_rules_maybe_job_with_a_closed_application_stays_out(
    world: World,
) -> None:
    closed = world.seed(world.alice)
    world.rate_by_rules(world.alice, closed, TriageVerdict.MAYBE)
    world.apply(world.alice, closed, ApplicationStatus.REJECTED)
    assert world.prepare(world.alice).jobs == ()


def test_the_agent_rating_replaces_the_rules_maybe_and_marks_it_as_the_agent(
    world: World,
) -> None:
    number = world.seed(world.alice)
    world.rate_by_rules(world.alice, number, TriageVerdict.MAYBE)
    world.save(world.alice, (number, 80, "analyse", "Fits"))
    triage = world.details(world.alice, number).triage
    assert triage is not None
    assert (triage.score, triage.verdict, triage.source) == (
        80,
        TriageVerdict.ANALYSE,
        TriageSource.AGENT,
    )
    assert world.prepare(world.alice).jobs == ()


def test_nothing_to_triage_gives_an_empty_brief(world: World) -> None:
    brief = world.prepare(world.alice)
    assert (brief.jobs, brief.pending) == ((), 0)


def test_the_brief_has_the_profile_and_the_rules_from_the_catalog(
    world: World,
) -> None:
    world.profiles[world.alice.user_id] = Profile(
        target=Target(roles=("Backend engineer",), min_salary_eur=60000)
    )
    brief = world.prepare(world.alice)
    assert brief.rules == RULES
    assert brief.profile is not None
    assert brief.profile.target == TargetData(
        roles=("Backend engineer",), min_salary_eur=60000
    )


def test_without_a_saved_profile_the_brief_has_an_empty_one(world: World) -> None:
    assert world.prepare(world.alice).profile == ProfileData()


def test_the_first_brief_has_the_confirmed_facts_as_kind_and_text(
    world: World,
) -> None:
    world.confirm(world.alice, FactKind.SKILL, "Python 8 years")
    world.confirm(world.alice, FactKind.EXPERIENCE, "Led a team of 5 at Acme")
    world.confirm(world.alice, FactKind.SKILL, "Rust (not sure yet)", confirmed=False)
    brief = world.prepare(world.alice)
    assert brief.facts == (
        TriageFactData(kind="skill", text="Python 8 years"),
        TriageFactData(kind="experience", text="Led a team of 5 at Acme"),
    )


def test_a_user_without_confirmed_facts_gets_an_empty_list_not_none(
    world: World,
) -> None:
    world.confirm(world.alice, FactKind.SKILL, "Unconfirmed", confirmed=False)
    assert world.prepare(world.alice).facts == ()


def test_the_facts_of_another_user_stay_out_of_the_brief(world: World) -> None:
    world.confirm(world.bob, FactKind.SKILL, "Bob knows Go")
    assert world.prepare(world.alice).facts == ()


def test_without_the_context_the_brief_has_only_the_jobs(world: World) -> None:
    world.profiles[world.alice.user_id] = Profile(target=Target(roles=("SRE",)))
    world.confirm(world.alice, FactKind.SKILL, "Python 8 years")
    number = world.seed(world.alice)
    brief = world.prepare(world.alice, include_context=False)
    assert (numbers_of(brief), brief.pending) == ([number], 1)
    assert (brief.profile, brief.rules, brief.facts) == (None, None, None)


def test_asking_for_the_context_again_brings_it_back(world: World) -> None:
    world.confirm(world.alice, FactKind.SKILL, "Python 8 years")
    world.seed(world.alice)
    world.prepare(world.alice)
    world.prepare(world.alice, include_context=False)
    again = world.prepare(world.alice, include_context=True)
    assert (again.profile, again.rules, again.facts) == (
        ProfileData(),
        RULES,
        (TriageFactData(kind="skill", text="Python 8 years"),),
    )


def test_a_user_does_not_see_the_jobs_of_another(world: World) -> None:
    world.seed(world.alice)
    brief = world.prepare(world.bob)
    assert (brief.jobs, brief.pending) == ((), 0)


# --- save_triage ------------------------------------------------------------


def test_saving_returns_every_item_and_the_ids_per_verdict(world: World) -> None:
    a, b, c, d = (world.seed(world.alice) for _ in range(4))
    saved = world.save(
        world.alice,
        (a, 90, "analyse", "Strong fit"),
        (b, 50, "maybe", "Short excerpt"),
        (c, 10, "skip", "Onsite Berlin"),
        (d, 70, "analyse", "Remote Python"),
    )
    assert [
        (t.job_number, t.score, t.verdict.value, t.reason) for t in saved.saved
    ] == [
        (a, 90, "analyse", "Strong fit"),
        (b, 50, "maybe", "Short excerpt"),
        (c, 10, "skip", "Onsite Berlin"),
        (d, 70, "analyse", "Remote Python"),
    ]
    assert saved.with_verdict(TriageVerdict.ANALYSE) == [a, d]
    assert saved.with_verdict(TriageVerdict.MAYBE) == [b]
    assert saved.with_verdict(TriageVerdict.SKIP) == [c]


def test_a_saved_triage_is_stamped_with_the_time_of_saving(world: World) -> None:
    number = world.seed(world.alice)
    saved = world.save(world.alice, (number, 60, "maybe", "Unsure"))
    assert saved.saved[0].triaged_at == world.clock.now()


def test_a_repeated_triage_overwrites_the_previous_one(world: World) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, (number, 20, "skip", "Looks wrong"))
    world.clock.advance(timedelta(days=1))
    world.save(world.alice, (number, 85, "analyse", "On a second look it fits"))
    triage = world.details(world.alice, number).triage
    assert triage is not None
    assert (triage.score, triage.verdict, triage.reason) == (
        85,
        TriageVerdict.ANALYSE,
        "On a second look it fits",
    )
    assert triage.triaged_at == world.clock.now()


def test_a_triaged_job_can_be_triaged_again_though_it_left_the_brief(
    world: World,
) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, (number, 20, "skip", "No"))
    assert (
        world.save(world.alice, (number, 30, "skip", "Still no")).saved[0].score == 30
    )


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ((), "Порожня пачка: потрібен хоч один елемент."),
    ],
)
def test_an_empty_batch_is_rejected(
    world: World, items: tuple[tuple[int, int, str, str], ...], message: str
) -> None:
    with pytest.raises(InvalidValue) as error:
        world.save(world.alice, *items)
    assert error.value.message == message


def test_more_than_5_items_are_rejected(world: World) -> None:
    numbers = [world.seed(world.alice) for _ in range(6)]
    with pytest.raises(InvalidValue) as error:
        world.save(world.alice, *((n, 50, "maybe", "ok") for n in numbers))
    assert error.value.message == "У пачці не більше 5 елементів."
    assert world.store.triage == {}


def test_exactly_5_items_are_saved(world: World) -> None:
    numbers = [world.seed(world.alice) for _ in range(5)]
    saved = world.save(world.alice, *((n, 50, "maybe", "ok") for n in numbers))
    assert len(saved.saved) == 5


def test_a_repeated_job_names_both_items(world: World) -> None:
    number = world.seed(world.alice)
    with pytest.raises(InvalidValue) as error:
        world.save(
            world.alice,
            (number, 50, "maybe", "ok"),
            (number, 60, "maybe", "again"),
        )
    assert error.value.message == f"Елемент 2: вакансія {number} уже є в елементі 1."


def test_an_unknown_job_names_the_item(world: World) -> None:
    number = world.seed(world.alice)
    with pytest.raises(InvalidValue) as error:
        world.save(world.alice, (number, 50, "maybe", "ok"), (99, 50, "maybe", "ok"))
    assert error.value.message == "Елемент 2: вакансію 99 не знайдено."


def test_a_job_of_another_user_is_not_found(world: World) -> None:
    theirs = world.seed(world.bob)
    with pytest.raises(InvalidValue) as error:
        world.save(world.alice, (theirs, 50, "maybe", "ok"))
    assert error.value.message == f"Елемент 1: вакансію {theirs} не знайдено."


def test_a_job_without_text_cannot_be_triaged(world: World) -> None:
    waiting = world.seed(world.alice, None)
    with pytest.raises(InvalidValue) as error:
        world.save(world.alice, (waiting, 50, "maybe", "ok"))
    assert error.value.message == (
        f"Елемент 1: у вакансії {waiting} нема тексту опису."
    )


@pytest.mark.parametrize(
    "status", [ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN]
)
def test_a_job_with_a_closed_application_cannot_be_triaged_and_nothing_is_saved(
    world: World, status: ApplicationStatus
) -> None:
    fine = world.seed(world.alice)
    closed = world.seed(world.alice)
    world.apply(world.alice, closed, status)
    with pytest.raises(InvalidValue) as error:
        world.save(world.alice, (fine, 50, "maybe", "ok"), (closed, 50, "maybe", "ok"))
    assert error.value.message == (
        f"Елемент 2: вакансію {closed} відхилено або відкликано в подачі."
    )
    assert world.details(world.alice, fine).triage is None


def test_a_foreign_closed_job_looks_like_an_unknown_one(world: World) -> None:
    theirs = world.seed(world.bob)
    world.apply(world.bob, theirs, ApplicationStatus.REJECTED)
    with pytest.raises(InvalidValue) as foreign:
        world.save(world.alice, (theirs, 50, "maybe", "ok"))
    with pytest.raises(InvalidValue) as missing:
        world.save(world.alice, (99, 50, "maybe", "ok"))
    assert foreign.value.message == f"Елемент 1: вакансію {theirs} не знайдено."
    assert missing.value.message == "Елемент 1: вакансію 99 не знайдено."


def test_a_job_with_an_active_application_can_be_triaged(world: World) -> None:
    active = world.seed(world.alice)
    world.apply(world.alice, active, ApplicationStatus.INTERVIEW)
    saved = world.save(world.alice, (active, 50, "maybe", "ok"))
    assert saved.saved[0].job_number == active


def test_an_invalid_score_names_the_item_and_the_job(world: World) -> None:
    first = world.seed(world.alice)
    second = world.seed(world.alice)
    with pytest.raises(InvalidValue) as error:
        world.save(
            world.alice, (first, 50, "maybe", "ok"), (second, 101, "maybe", "ok")
        )
    assert error.value.message == (
        f"Елемент 2 (вакансія {second}): скор — ціле число від 0 до 100."
    )


def test_one_bad_item_saves_nothing(world: World) -> None:
    first = world.seed(world.alice)
    second = world.seed(world.alice)
    with pytest.raises(InvalidValue):
        world.save(world.alice, (first, 50, "maybe", "ok"), (second, 50, "great", "ok"))
    assert world.details(world.alice, first).triage is None
    assert numbers_of(world.prepare(world.alice)) == [second, first]


def test_an_unknown_job_late_in_the_batch_saves_nothing(world: World) -> None:
    first = world.seed(world.alice)
    with pytest.raises(InvalidValue):
        world.save(world.alice, (first, 50, "maybe", "ok"), (42, 50, "maybe", "ok"))
    assert world.details(world.alice, first).triage is None


def test_a_user_cannot_see_or_overwrite_the_triage_of_another(world: World) -> None:
    world.seed(world.alice)
    mine = world.seed(world.alice)
    theirs = world.seed(world.bob)
    world.save(world.alice, (mine, 90, "analyse", "Fit"))
    assert world.details(world.bob, theirs).triage is None
    assert [item.triage_verdict for item in world.listed(world.bob)] == [None]
    # Номери рахуються на користувача: у Боба є лише вакансія 1, «чужої» 2 для нього нема.
    with pytest.raises(InvalidValue) as error:
        world.save(world.bob, (mine, 1, "skip", "Not mine"))
    assert error.value.message == f"Елемент 1: вакансію {mine} не знайдено."
    assert world.details(world.alice, mine).triage is not None


# --- тріаж у списку й деталях ------------------------------------------------


def test_the_summary_carries_the_score_the_verdict_and_the_reason(
    world: World,
) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, (number, 33, "skip", "Onsite Berlin"))
    [item] = world.listed(world.alice)
    assert (item.triage_score, item.triage_verdict, item.triage_reason) == (
        33,
        TriageVerdict.SKIP,
        "Onsite Berlin",
    )


def test_an_untriaged_job_has_no_triage_in_the_list(world: World) -> None:
    world.seed(world.alice)
    [item] = world.listed(world.alice)
    assert (item.triage_score, item.triage_verdict, item.triage_reason) == (
        None,
        None,
        None,
    )


def test_a_skip_verdict_does_not_hide_the_job(world: World) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, (number, 5, "skip", "Wrong stack"))
    assert world.numbers(world.alice) == [number]
    assert world.numbers(world.alice, dismissed=True) == []


def test_the_list_goes_analyse_then_maybe_then_skip_then_untriaged(
    world: World,
) -> None:
    skip = world.seed(world.alice)
    plain_old = world.seed(world.alice)
    maybe = world.seed(world.alice)
    analyse = world.seed(world.alice)
    plain_new = world.seed(world.alice)
    world.save(
        world.alice,
        (skip, 99, "skip", "r"),
        (maybe, 10, "maybe", "r"),
        (analyse, 1, "analyse", "r"),
    )
    assert world.numbers(world.alice) == [analyse, maybe, skip, plain_new, plain_old]


def test_inside_a_verdict_the_higher_triage_score_comes_first(world: World) -> None:
    low = world.seed(world.alice)
    high = world.seed(world.alice)
    mid = world.seed(world.alice)
    world.save(
        world.alice,
        (low, 66, "analyse", "r"),
        (high, 95, "analyse", "r"),
        (mid, 80, "analyse", "r"),
    )
    assert world.numbers(world.alice) == [high, mid, low]


def test_equal_scores_fall_back_to_newest_first(world: World) -> None:
    old = world.seed(world.alice)
    new = world.seed(world.alice)
    world.save(world.alice, (old, 70, "maybe", "r"), (new, 70, "maybe", "r"))
    assert world.numbers(world.alice) == [new, old]


def test_jobs_that_need_text_stay_last_whatever_the_triage_of_others(
    world: World,
) -> None:
    waiting = world.seed(world.alice, None)
    skip = world.seed(world.alice)
    world.save(world.alice, (skip, 1, "skip", "r"))
    assert world.numbers(world.alice) == [skip, waiting]


@pytest.mark.parametrize("verdict", ["analyse", "maybe", "skip"])
def test_the_verdict_filter_keeps_only_that_verdict(world: World, verdict: str) -> None:
    ids_by_verdict = {
        name: world.seed(world.alice) for name in ("analyse", "maybe", "skip")
    }
    world.seed(world.alice)  # без тріажу
    world.save(
        world.alice,
        *((number, 50, name, "r") for name, number in ids_by_verdict.items()),
    )
    assert world.numbers(world.alice, triage_verdict=verdict) == [
        ids_by_verdict[verdict]
    ]


def test_an_unknown_verdict_filter_is_rejected(world: World) -> None:
    with pytest.raises(InvalidFields) as error:
        world.listed(world.alice, triage_verdict="great")
    assert error.value.problems[0].field == "triage_verdict"
    assert error.value.message == "Невідомий вердикт тріажу."


def test_the_details_of_an_untriaged_job_have_no_triage(world: World) -> None:
    number = world.seed(world.alice)
    assert world.details(world.alice, number).triage is None


def test_the_details_carry_the_whole_triage(world: World) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, (number, 72, "analyse", "Remote Python"))
    triage = world.details(world.alice, number).triage
    assert triage is not None
    assert (
        triage.job_number,
        triage.score,
        triage.verdict,
        triage.reason,
        triage.triaged_at,
        triage.source,
    ) == (
        number,
        72,
        TriageVerdict.ANALYSE,
        "Remote Python",
        world.clock.now(),
        TriageSource.AGENT,
    )
