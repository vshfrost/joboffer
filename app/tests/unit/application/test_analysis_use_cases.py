"""Use cases аналізу: бриф для Claude, збереження з фільтрами профілю, застарілість, список, тріаж.

Семантика і тексти помилок — як у v1 (`origin/main` `99a2007`).
"""

from datetime import datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.analysis.use_cases import AnalysisUseCases
from application.contracts.actor import Actor, Channel, Scope
from application.contracts.analysis import (
    AnalogueData,
    AnalogueInput,
    AnalysisBriefData,
    AnalysisData,
    AnalysisInput,
    GapAnaloguesData,
    GapAnaloguesInput,
    GapData,
    GapInput,
    KeywordFactsData,
)
from application.contracts.jobs import JobSearchInput, JobSummaryData
from application.contracts.profile import (
    ContactsData,
    LocationsData,
    ProfileData,
    RulesData,
    SectionData,
    TargetData,
)
from application.contracts.triage import TriageInput
from application.jobs.use_cases import JobUseCases
from application.ports.prompts import PromptKey
from application.profile.use_cases import ProfileUseCases
from application.triage.use_cases import TriageUseCases
from domain.facts.fact import NewFact
from domain.facts.ids import FactId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.profile.modes import Seniority, WorkMode
from domain.profile.profile import Profile
from domain.shared.errors import InvalidFields, InvalidValue, NotFound
from tests.support.analysis import InMemoryAnalysisUnitOfWork
from tests.support.clock import FakeClock
from tests.support.facts import InMemoryFactUnitOfWork
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store
from tests.support.profile import InMemoryProfileUnitOfWork
from tests.support.triage import InMemoryTriageUnitOfWork

TEMPLATE = (
    "Score for {candidate}. Domain fit with target domains{domain_examples}; "
    "gaps: what {candidate} lacks."
)
RULES = "Quick triage rules."


class FakePrompts:
    """Шаблон рубрики з іменованими плейсхолдерами — як у каталозі промптів."""

    def __init__(self, rubric: str = TEMPLATE) -> None:
        self._rubric = rubric

    def get(self, key: PromptKey) -> str:
        return {PromptKey.ANALYSIS_RUBRIC: self._rubric, PromptKey.TRIAGE_RULES: RULES}[
            key
        ]


class World:
    def __init__(
        self,
        portal: BlockingPortal,
        clock: FakeClock,
        ids: SequentialIds,
        rubric: str = TEMPLATE,
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.jobs_store = Store.empty()
        self.facts_store = FactStore.empty()
        self.profiles: dict[UserId, Profile] = {}
        self.saved_at: dict[UserId, datetime] = {}
        self.inputs_changed: dict[UserId, datetime] = {}
        self.alice = self._actor()
        self.bob = self._actor()
        prompts = FakePrompts(rubric)
        self.analysis = AnalysisUseCases(
            lambda: InMemoryAnalysisUnitOfWork(
                self.jobs_store, self.facts_store, self.profiles, self.inputs_changed
            ),
            clock,
            ids,
            prompts,
        )
        self.jobs = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.jobs_store), clock, ids
        )
        self.triage = TriageUseCases(
            lambda: InMemoryTriageUnitOfWork(
                self.jobs_store, self.profiles, self.inputs_changed
            ),
            clock,
            ids,
            prompts,
        )
        self.profile = ProfileUseCases(
            lambda: InMemoryProfileUnitOfWork(
                self.profiles, self.saved_at, self.inputs_changed
            ),
            clock,
        )

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
    ) -> int:
        self.clock.advance(timedelta(minutes=1))

        async def run() -> int:
            async with InMemoryJobUnitOfWork(self.jobs_store) as uow:
                number = await uow.jobs.add(
                    actor.user_id,
                    JobId(self.ids.new()),
                    NewJob(text=text, title=title, company=company),
                    self.clock.now(),
                )
                await uow.commit()
                return number

        return self.portal.call(run)

    def fact(self, actor: Actor, kind: str, text: str, *, confirmed: bool) -> int:
        async def run() -> int:
            async with InMemoryFactUnitOfWork(self.facts_store) as uow:
                added = await uow.facts.add(
                    actor.user_id,
                    FactId(self.ids.new()),
                    NewFact.parse(kind=kind, text=text),
                    self.clock.now(),
                )
                if confirmed:
                    await uow.facts.confirm(
                        actor.user_id, [added.number], self.clock.now()
                    )
                await uow.commit()
                return added.number

        return self.portal.call(run)

    def prepare(self, actor: Actor, number: int) -> AnalysisBriefData:
        return self.portal.call(self.analysis.prepare_analysis, actor, number)

    def save(self, actor: Actor, number: int, **fields: object) -> AnalysisData:
        data = AnalysisInput(**({"score": 70, "summary": "A backend role."} | fields))  # type: ignore[arg-type]
        return self.portal.call(self.analysis.save_analysis, actor, number, data)

    def get(self, actor: Actor, number: int) -> AnalysisData:
        return self.portal.call(self.analysis.get_analysis, actor, number)

    def listed(self, actor: Actor, **fields: object) -> list[JobSummaryData]:
        data = JobSearchInput(**fields)  # type: ignore[arg-type]
        return self.portal.call(self.jobs.list_jobs, actor, data)

    def numbers(self, actor: Actor, **fields: object) -> list[int]:
        return [item.job_number for item in self.listed(actor, **fields)]

    def triage_job(self, actor: Actor, number: int, score: int, verdict: str) -> None:
        self.portal.call(
            self.triage.save_triage,
            actor,
            [TriageInput(job_number=number, score=score, verdict=verdict, reason="r")],
        )

    def set_profile(self, actor: Actor, **sections: SectionData) -> None:
        """Зберігає розділи профілю через use case (так, як це робить веб чи MCP)."""
        for section in sections.values():
            self.portal.call(self.profile.save_section, actor, section)


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


# --- prepare_analysis ---------------------------------------------------------


def test_a_missing_job_is_not_found(world: World) -> None:
    with pytest.raises(NotFound) as error:
        world.prepare(world.alice, 9)
    assert error.value.message == "Вакансію 9 не знайдено."


def test_a_job_of_another_user_is_not_found(world: World) -> None:
    theirs = world.seed(world.bob)
    world.seed(world.alice)
    with pytest.raises(NotFound):
        world.prepare(world.alice, theirs + 1)


def test_a_job_without_text_is_refused_with_the_v1_text(world: World) -> None:
    waiting = world.seed(world.alice, None)
    with pytest.raises(InvalidValue) as error:
        world.prepare(world.alice, waiting)
    assert error.value.message == (
        f"У вакансії {waiting} нема тексту опису (вона з листа-алерту): спершу додай текст."
    )


def test_the_brief_has_the_job_and_its_text(world: World) -> None:
    number = world.seed(world.alice, "Go role", title="Go Dev", company="Acme")
    brief = world.prepare(world.alice, number)
    assert (brief.job.job_number, brief.job.title, brief.job.text) == (
        number,
        "Go Dev",
        "Go role",
    )


def test_the_brief_carries_only_confirmed_facts_by_kind_then_number(
    world: World,
) -> None:
    number = world.seed(world.alice)
    skill_1 = world.fact(world.alice, "skill", "Python", confirmed=True)
    world.fact(world.alice, "skill", "Rust", confirmed=False)
    experience = world.fact(
        world.alice, "experience", "5 years at Acme", confirmed=True
    )
    skill_2 = world.fact(world.alice, "skill", "Postgres", confirmed=True)
    language = world.fact(world.alice, "language", "English C1", confirmed=True)
    world.fact(world.bob, "skill", "Not mine", confirmed=True)

    brief = world.prepare(world.alice, number)

    assert [fact.fact_number for fact in brief.confirmed_facts] == [
        experience,
        skill_1,
        skill_2,
        language,
    ]
    assert [fact.text for fact in brief.confirmed_facts] == [
        "5 years at Acme",
        "Python",
        "Postgres",
        "English C1",
    ]


def test_the_brief_has_the_profile_and_an_empty_one_when_none_is_saved(
    world: World,
) -> None:
    number = world.seed(world.alice)
    assert world.prepare(world.alice, number).profile == ProfileData()
    world.set_profile(world.alice, target=TargetData(roles=("Backend",)))
    assert world.prepare(world.alice, number).profile.target.roles == ("Backend",)


def test_the_rubric_names_the_candidate_and_gives_domain_examples(
    world: World,
) -> None:
    number = world.seed(world.alice)
    world.set_profile(
        world.alice,
        target=TargetData(target_domains=("fintech", "payments")),
        contacts=ContactsData(full_name="Test User"),
    )
    assert world.prepare(world.alice, number).rubric == (
        "Score for Test User. Domain fit with target domains (e.g. fintech, payments); "
        "gaps: what Test User lacks."
    )


def test_an_empty_profile_gives_a_neutral_rubric_without_examples(
    world: World,
) -> None:
    number = world.seed(world.alice)
    assert world.prepare(world.alice, number).rubric == (
        "Score for the candidate. Domain fit with target domains; "
        "gaps: what the candidate lacks."
    )


# --- save_analysis ------------------------------------------------------------


def test_a_saved_analysis_comes_back_with_filters_and_the_time(world: World) -> None:
    number = world.seed(world.alice)
    saved = world.save(
        world.alice,
        number,
        score=82,
        summary="  A  backend\n role. ",
        must_have=["Python", "python"],
        work_mode="remote",
        seniority="senior",
        salary_max_eur=90000,
    )
    assert (saved.job_number, saved.score, saved.summary) == (
        number,
        82,
        "A backend role.",
    )
    assert saved.must_have == ("Python",)
    assert (saved.work_mode, saved.seniority) == (WorkMode.REMOTE, Seniority.SENIOR)
    assert (saved.filters_passed, saved.flags) == (True, ())
    assert saved.updated_at == world.clock.now()
    assert saved.stale_since is None


def test_hard_filters_of_the_profile_become_flags(world: World) -> None:
    number = world.seed(
        world.alice, "Backend. We love crypto.", title="Dev", company="Acme"
    )
    world.set_profile(
        world.alice,
        target=TargetData(seniority=("senior",), min_salary_eur=90000),
        locations=LocationsData(work_modes=("remote",)),
        rules=RulesData(stop_words=("crypto",)),
    )
    saved = world.save(
        world.alice,
        number,
        work_mode="onsite",
        seniority="junior",
        salary_max_eur=50000,
    )
    assert saved.filters_passed is False
    assert saved.flags == (
        "Формат onsite — не з профілю.",
        "Рівень junior — не з профілю.",
        "ЗП до 50000 EUR — менше мінімуму 90000 EUR.",
        "Стоп-слово: crypto.",
    )


def test_the_title_and_company_are_part_of_the_posting_for_stop_words(
    world: World,
) -> None:
    number = world.seed(
        world.alice, "Plain text.", title="Gambling Backend", company="X"
    )
    world.set_profile(world.alice, rules=RulesData(stop_words=("gambling",)))
    assert world.save(world.alice, number).flags == ("Стоп-слово: gambling.",)


def test_a_repeated_analysis_replaces_the_previous_one(world: World) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, number, score=30, summary="First.")
    world.clock.advance(timedelta(days=1))
    world.save(world.alice, number, score=90, summary="Second.")
    current = world.get(world.alice, number)
    assert (current.score, current.summary) == (90, "Second.")
    assert current.updated_at == world.clock.now()


def test_gaps_come_back_numbered_from_1_with_their_questions(world: World) -> None:
    number = world.seed(world.alice)
    saved = world.save(
        world.alice,
        number,
        gaps=[
            GapInput(gap="Kubernetes", question="Чи працювали з Kubernetes?"),
            GapInput(gap="Go", question="Чи писали на Go?"),
        ],
    )
    expected = (
        GapData(number=1, gap="Kubernetes", question="Чи працювали з Kubernetes?"),
        GapData(number=2, gap="Go", question="Чи писали на Go?"),
    )
    assert saved.gaps == expected
    assert world.get(world.alice, number).gaps == expected


def test_the_old_format_of_gaps_is_accepted_with_no_questions(world: World) -> None:
    number = world.seed(world.alice)
    saved = world.save(world.alice, number, gaps=["Kubernetes", "Go"])
    assert saved.gaps == (
        GapData(number=1, gap="Kubernetes", question=None),
        GapData(number=2, gap="Go", question=None),
    )
    assert world.get(world.alice, number).gaps == saved.gaps


def test_the_brief_shows_the_previous_gaps_with_questions(world: World) -> None:
    number = world.seed(world.alice)
    world.save(
        world.alice, number, gaps=[GapInput(gap="Go", question="Чи писали на Go?")]
    )
    previous = world.prepare(world.alice, number).previous
    assert previous is not None
    assert previous.gaps == (GapData(number=1, gap="Go", question="Чи писали на Go?"),)


def test_a_repeated_save_replaces_the_gaps_of_the_previous_one(world: World) -> None:
    number = world.seed(world.alice)
    world.save(
        world.alice, number, gaps=[GapInput(gap="Go", question="Чи писали на Go?")]
    )
    world.save(
        world.alice,
        number,
        gaps=[GapInput(gap="Rust", question="Чи писали на Rust?")],
    )
    assert world.get(world.alice, number).gaps == (
        GapData(number=1, gap="Rust", question="Чи писали на Rust?"),
    )


def test_an_analysis_without_gaps_saves_and_reads_back_without_errors(
    world: World,
) -> None:
    number = world.seed(world.alice)
    assert world.save(world.alice, number, gaps=[]).gaps == ()
    assert world.get(world.alice, number).gaps == ()


@pytest.mark.parametrize("keyword", ["Java | ", "a | b | c | d | e | f"])
def test_a_bad_keyword_group_is_refused_and_saves_nothing(
    world: World, keyword: str
) -> None:
    number = world.seed(world.alice)

    with pytest.raises(InvalidValue):
        world.save(world.alice, number, keywords=["Python", keyword])

    with pytest.raises(NotFound):
        world.get(world.alice, number)


def test_a_keyword_group_is_saved_and_read_back_as_one_keyword(world: World) -> None:
    number = world.seed(world.alice)

    world.save(world.alice, number, keywords=["Java|Python", "Kafka"])

    assert world.get(world.alice, number).keywords == ("Java | Python", "Kafka")


def test_what_the_employer_asks_of_candidates_is_saved_and_read_back(
    world: World,
) -> None:
    number = world.seed(world.alice)
    asks = ["Send your GitHub", "Describe a project you are proud of"]

    saved = world.save(world.alice, number, candidate_asks=[*asks, " send your github"])

    assert saved.candidate_asks == tuple(asks)
    assert world.get(world.alice, number).candidate_asks == tuple(asks)
    previous = world.prepare(world.alice, number).previous
    assert previous is not None
    assert previous.candidate_asks == tuple(asks)


def test_an_analysis_saved_without_asks_reads_back_with_none(world: World) -> None:
    number = world.seed(world.alice)

    assert world.save(world.alice, number).candidate_asks == ()
    assert world.get(world.alice, number).candidate_asks == ()


def test_a_repeated_save_replaces_the_asks(world: World) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, number, candidate_asks=["Send your GitHub"])

    world.save(world.alice, number)

    assert world.get(world.alice, number).candidate_asks == ()


def test_the_fact_map_is_saved_with_the_analysis_and_read_back(world: World) -> None:
    number = world.seed(world.alice)
    python = world.fact(world.alice, "skill", "Python", confirmed=True)
    kafka = world.fact(world.alice, "skill", "Kafka", confirmed=True)

    world.save(
        world.alice,
        number,
        keywords=["Python", "Kafka", "Go"],
        keyword_facts={"Python": [python, kafka], "Kafka": [kafka]},
    )

    assert world.get(world.alice, number).keyword_facts == (
        KeywordFactsData(keyword="Python", fact_numbers=(python, kafka)),
        KeywordFactsData(keyword="Kafka", fact_numbers=(kafka,)),
    )


def test_an_analysis_saved_without_the_map_reads_back_without_one(
    world: World,
) -> None:
    number = world.seed(world.alice)

    world.save(world.alice, number, keywords=["Python"])

    assert world.get(world.alice, number).keyword_facts is None


def test_a_fact_id_that_does_not_exist_in_the_map_is_refused_and_saves_nothing(
    world: World,
) -> None:
    number = world.seed(world.alice)
    python = world.fact(world.alice, "skill", "Python", confirmed=True)

    with pytest.raises(InvalidValue) as error:
        world.save(
            world.alice,
            number,
            keywords=["Python", "Kafka"],
            keyword_facts={"Python": [python], "Kafka": [99]},
        )

    assert error.value.message == "Факти не знайдено: #99."
    with pytest.raises(NotFound):
        world.get(world.alice, number)


def test_a_fact_of_another_user_in_the_map_is_refused_like_a_missing_one(
    world: World,
) -> None:
    number = world.seed(world.alice)
    theirs = world.fact(world.bob, "skill", "Kafka", confirmed=True)

    with pytest.raises(InvalidValue):
        world.save(
            world.alice,
            number,
            keywords=["Kafka"],
            keyword_facts={"Kafka": [theirs]},
        )


def test_a_gap_without_a_question_is_refused_with_its_number_and_saves_nothing(
    world: World,
) -> None:
    number = world.seed(world.alice)
    with pytest.raises(InvalidValue) as error:
        world.save(
            world.alice,
            number,
            gaps=[
                GapInput(gap="Go", question="Чи писали на Go?"),
                GapInput(gap="Rust"),
            ],
        )
    assert error.value.message == "gaps: у прогалини 2 нема питання."
    with pytest.raises(NotFound):
        world.get(world.alice, number)


def test_a_too_long_question_is_refused_with_the_number_of_its_gap(
    world: World,
) -> None:
    number = world.seed(world.alice)
    with pytest.raises(InvalidValue) as error:
        world.save(world.alice, number, gaps=[GapInput(gap="Go", question="q" * 301)])
    assert error.value.message == "gaps: питання прогалини 1 довше за 300 символів."


def test_flags_are_a_snapshot_the_profile_does_not_rewrite(world: World) -> None:
    number = world.seed(world.alice, "Crypto backend.")
    world.set_profile(world.alice, rules=RulesData(stop_words=("crypto",)))
    world.save(world.alice, number)
    world.set_profile(world.alice, rules=RulesData(stop_words=()))
    assert world.get(world.alice, number).flags == ("Стоп-слово: crypto.",)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"score": 101}, "Скор — ціле число від 0 до 100."),
        ({"score": -1}, "Скор — ціле число від 0 до 100."),
        ({"summary": "  "}, "summary — від 1 до 1000 символів."),
        (
            {"salary_min_eur": 9, "salary_max_eur": 5},
            "salary_min_eur більша за salary_max_eur.",
        ),
        ({"must_have": ["x" * 301]}, "must_have: кожен пункт — від 1 до 300 символів."),
        (
            {"candidate_asks": ["x" * 301]},
            "candidate_asks: кожен пункт — від 1 до 300 символів.",
        ),
        (
            {"candidate_asks": [f"ask {n}" for n in range(31)]},
            "candidate_asks — не більше 30 пунктів.",
        ),
        (
            {"work_mode": "office"},
            "work_mode: 'office' — допустимо remote, hybrid, onsite або порожньо.",
        ),
    ],
)
def test_an_invalid_analysis_saves_nothing(
    world: World, fields: dict[str, object], message: str
) -> None:
    number = world.seed(world.alice)
    with pytest.raises(InvalidValue) as error:
        world.save(world.alice, number, **fields)
    assert error.value.message == message
    with pytest.raises(NotFound):
        world.get(world.alice, number)


def test_saving_for_a_missing_or_foreign_job_is_not_found(world: World) -> None:
    theirs = world.seed(world.bob)
    with pytest.raises(NotFound) as error:
        world.save(world.alice, theirs)
    assert error.value.message == f"Вакансію {theirs} не знайдено."


def test_the_brief_shows_the_previous_analysis(world: World) -> None:
    number = world.seed(world.alice)
    assert world.prepare(world.alice, number).previous is None
    world.save(world.alice, number, score=55, summary="Before.")
    previous = world.prepare(world.alice, number).previous
    assert previous is not None
    assert (previous.score, previous.summary) == (55, "Before.")


# --- get_analysis і застарілість ------------------------------------------------


def test_an_unanalysed_job_has_no_analysis(world: World) -> None:
    number = world.seed(world.alice)
    with pytest.raises(NotFound):
        world.get(world.alice, number)


def test_an_analysis_of_another_user_is_not_found(world: World) -> None:
    mine = world.seed(world.alice)
    world.seed(world.bob)
    world.save(world.alice, mine)
    with pytest.raises(NotFound):
        world.get(world.bob, mine)


def test_an_analysis_is_fresh_while_the_profile_is_untouched(world: World) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, number)
    assert world.get(world.alice, number).stale_since is None


@pytest.mark.parametrize(
    "change",
    [
        TargetData(roles=("QA",)),
        LocationsData(relocation=True),
        RulesData(stop_words=("crypto",)),
    ],
    ids=["target", "locations", "rules"],
)
def test_a_change_of_target_locations_or_rules_makes_the_analysis_stale(
    world: World, change: SectionData
) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, number)
    world.clock.advance(timedelta(days=2))
    world.set_profile(world.alice, section=change)
    assert world.get(world.alice, number).stale_since == world.clock.now()


def test_a_change_of_contacts_does_not(world: World) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, number)
    world.clock.advance(timedelta(days=2))
    world.set_profile(world.alice, contacts=ContactsData(full_name="Test User"))
    assert world.get(world.alice, number).stale_since is None


def test_saving_a_section_without_real_changes_does_not(world: World) -> None:
    world.set_profile(world.alice, target=TargetData(roles=("QA",)))
    number = world.seed(world.alice)
    world.save(world.alice, number)
    world.clock.advance(timedelta(days=2))
    world.set_profile(world.alice, target=TargetData(roles=("QA",)))
    assert world.get(world.alice, number).stale_since is None


def test_a_change_made_before_the_analysis_does_not_make_it_stale(
    world: World,
) -> None:
    number = world.seed(world.alice)
    world.set_profile(world.alice, target=TargetData(roles=("QA",)))
    world.clock.advance(timedelta(days=1))
    world.save(world.alice, number)
    assert world.get(world.alice, number).stale_since is None


def test_a_new_analysis_clears_the_mark(world: World) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, number)
    world.clock.advance(timedelta(days=1))
    world.set_profile(world.alice, target=TargetData(roles=("QA",)))
    assert world.get(world.alice, number).stale_since is not None
    world.clock.advance(timedelta(days=1))
    world.save(world.alice, number)
    assert world.get(world.alice, number).stale_since is None


def test_stale_since_is_the_time_of_the_latest_change(world: World) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, number)
    world.clock.advance(timedelta(days=1))
    world.set_profile(world.alice, target=TargetData(roles=("QA",)))
    world.clock.advance(timedelta(days=1))
    world.set_profile(world.alice, rules=RulesData(stop_words=("x",)))
    assert world.get(world.alice, number).stale_since == world.clock.now()


def test_replacing_the_whole_profile_marks_only_a_real_change(world: World) -> None:
    number = world.seed(world.alice)
    base = ProfileData(target=TargetData(roles=("QA",)))
    world.portal.call(world.profile.replace_profile, world.alice, base)
    world.save(world.alice, number)
    world.clock.advance(timedelta(days=1))
    same = ProfileData(
        target=TargetData(roles=("QA",)), contacts=ContactsData(full_name="Test User")
    )
    world.portal.call(world.profile.replace_profile, world.alice, same)
    assert world.get(world.alice, number).stale_since is None
    world.clock.advance(timedelta(days=1))
    changed = ProfileData(target=TargetData(roles=("SRE",)))
    world.portal.call(world.profile.replace_profile, world.alice, changed)
    assert world.get(world.alice, number).stale_since == world.clock.now()


def test_the_profile_of_another_user_does_not_make_an_analysis_stale(
    world: World,
) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, number)
    world.clock.advance(timedelta(days=1))
    world.set_profile(world.bob, target=TargetData(roles=("QA",)))
    assert world.get(world.alice, number).stale_since is None


# --- список -------------------------------------------------------------------


def test_the_summary_carries_score_filters_and_work_mode(world: World) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, number, score=64, work_mode="hybrid")
    [item] = world.listed(world.alice)
    assert (item.score, item.filters_passed, item.work_mode) == (
        64,
        True,
        WorkMode.HYBRID,
    )


def test_an_unanalysed_job_has_no_score_in_the_list(world: World) -> None:
    world.seed(world.alice)
    [item] = world.listed(world.alice)
    assert (item.score, item.filters_passed, item.work_mode) == (None, None, None)


def test_a_score_of_zero_is_a_real_score_in_the_list(world: World) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, number, score=0)
    [item] = world.listed(world.alice)
    assert item.score == 0


def test_the_list_follows_the_v1_order_over_every_state(world: World) -> None:
    waiting = world.seed(world.alice, None)
    plain_old = world.seed(world.alice)
    skip = world.seed(world.alice)
    maybe_low = world.seed(world.alice)
    maybe_high = world.seed(world.alice)
    analyse = world.seed(world.alice)
    plain_new = world.seed(world.alice)
    failed_high = world.seed(world.alice)
    passed_low = world.seed(world.alice)
    passed_high = world.seed(world.alice)
    world.triage_job(world.alice, skip, 99, "skip")
    world.triage_job(world.alice, maybe_low, 10, "maybe")
    world.triage_job(world.alice, maybe_high, 70, "maybe")
    world.triage_job(world.alice, analyse, 1, "analyse")
    world.set_profile(world.alice, locations=LocationsData(work_modes=("remote",)))
    world.save(world.alice, passed_low, score=40, work_mode="remote")
    world.save(world.alice, passed_high, score=85, work_mode="remote")
    world.save(world.alice, failed_high, score=99, work_mode="onsite")

    assert world.numbers(world.alice) == [
        passed_high,
        passed_low,
        failed_high,
        analyse,
        maybe_high,
        maybe_low,
        skip,
        plain_new,
        plain_old,
        waiting,
    ]


def test_an_analysed_job_keeps_its_old_triage_after_the_analysis(world: World) -> None:
    number = world.seed(world.alice)
    world.triage_job(world.alice, number, 77, "analyse")
    world.save(world.alice, number, score=50)
    [item] = world.listed(world.alice)
    assert (item.score, item.triage_score, item.triage_verdict) == (50, 77, "analyse")


def test_equal_scores_fall_back_to_the_newest_first(world: World) -> None:
    old = world.seed(world.alice)
    new = world.seed(world.alice)
    world.save(world.alice, old, score=60)
    world.save(world.alice, new, score=60)
    assert world.numbers(world.alice) == [new, old]


def test_the_work_mode_filter_uses_the_analysis_and_skips_unanalysed_jobs(
    world: World,
) -> None:
    remote = world.seed(world.alice)
    onsite = world.seed(world.alice)
    world.seed(world.alice)
    world.save(world.alice, remote, work_mode="remote")
    world.save(world.alice, onsite, work_mode="onsite")
    assert world.numbers(world.alice, work_mode="remote") == [remote]
    assert world.numbers(world.alice, work_mode="hybrid") == []


def test_an_unknown_work_mode_filter_is_rejected(world: World) -> None:
    with pytest.raises(InvalidFields) as error:
        world.listed(world.alice, work_mode="office")
    assert error.value.problems[0].field == "work_mode"
    assert error.value.message == "Невідомий формат роботи."


def test_a_user_does_not_see_the_analyses_of_another_in_the_list(
    world: World,
) -> None:
    mine = world.seed(world.alice)
    world.seed(world.bob)
    world.save(world.alice, mine, score=88)
    [item] = world.listed(world.bob)
    assert (item.score, item.filters_passed) == (None, None)


# --- зв'язок із тріажем -------------------------------------------------------------


def test_an_analysed_job_is_not_a_triage_candidate(world: World) -> None:
    analysed = world.seed(world.alice)
    waiting = world.seed(world.alice)
    world.save(world.alice, analysed)
    brief = world.portal.call(world.triage.prepare_triage, world.alice, 5)
    assert [job.job_number for job in brief.jobs] == [waiting]
    assert brief.pending == 1


def test_an_analysed_job_cannot_be_triaged(world: World) -> None:
    number = world.seed(world.alice)
    world.save(world.alice, number)
    with pytest.raises(InvalidValue) as error:
        world.triage_job(world.alice, number, 50, "maybe")
    assert error.value.message == f"Елемент 1: вакансію {number} уже проаналізовано."


# --- аналоги прогалин ---------------------------------------------------------------


def test_gap_analogues_are_saved_with_the_analysis_and_read_back(world: World) -> None:
    number = world.seed(world.alice)
    prometheus = world.fact(world.alice, "skill", "Prometheus", confirmed=True)
    grafana = world.fact(world.alice, "skill", "Grafana", confirmed=True)

    saved = world.save(
        world.alice,
        number,
        gaps=[
            GapInput(gap="OpenTelemetry", question="Have you used OpenTelemetry?"),
            GapInput(gap="gRPC", question="Have you used gRPC?"),
        ],
        gap_analogues=[
            GapAnaloguesInput(
                gap="OpenTelemetry",
                analogues=[
                    AnalogueInput(
                        fact_numbers=[prometheus, grafana],
                        explanation="Metrics and dashboards in production",
                    )
                ],
            )
        ],
    )

    expected = (
        GapAnaloguesData(
            gap="OpenTelemetry",
            analogues=(
                AnalogueData(
                    fact_numbers=(prometheus, grafana),
                    explanation="Metrics and dashboards in production",
                ),
            ),
            no_honest_analogue=False,
        ),
        GapAnaloguesData(gap="gRPC", analogues=(), no_honest_analogue=True),
    )
    previous = world.prepare(world.alice, number).previous
    assert saved.gap_analogues == expected
    assert world.get(world.alice, number).gap_analogues == expected
    assert previous is not None
    assert previous.gap_analogues == expected


def test_an_analysis_saved_without_gap_analogues_reads_back_without_them(
    world: World,
) -> None:
    number = world.seed(world.alice)

    world.save(world.alice, number, gaps=["Go"])

    assert world.get(world.alice, number).gap_analogues is None


def test_a_resave_without_gap_analogues_replaces_the_earlier_ones(
    world: World,
) -> None:
    number = world.seed(world.alice)
    rest = world.fact(world.alice, "skill", "REST", confirmed=True)
    analogue = AnalogueInput(fact_numbers=[rest], explanation="REST services")
    world.save(
        world.alice,
        number,
        gaps=["gRPC"],
        gap_analogues=[GapAnaloguesInput(gap="gRPC", analogues=[analogue])],
    )

    world.save(world.alice, number, gaps=["gRPC"])

    assert world.get(world.alice, number).gap_analogues is None


def test_an_unconfirmed_fact_in_gap_analogues_is_refused_and_saves_nothing(
    world: World,
) -> None:
    number = world.seed(world.alice)
    draft = world.fact(world.alice, "skill", "REST", confirmed=False)
    analogue = AnalogueInput(fact_numbers=[draft], explanation="REST services")

    with pytest.raises(InvalidValue) as error:
        world.save(
            world.alice,
            number,
            gaps=["gRPC"],
            gap_analogues=[GapAnaloguesInput(gap="gRPC", analogues=[analogue])],
        )

    assert error.value.message == (
        f"Факти не підтверджені: #{draft} — спершу користувач їх підтверджує."
    )
    with pytest.raises(NotFound):
        world.get(world.alice, number)


def test_a_fact_of_another_user_in_gap_analogues_is_refused_like_a_missing_one(
    world: World,
) -> None:
    number = world.seed(world.alice)
    theirs = world.fact(world.bob, "skill", "REST", confirmed=True)
    analogue = AnalogueInput(fact_numbers=[theirs], explanation="REST services")

    with pytest.raises(InvalidValue) as error:
        world.save(
            world.alice,
            number,
            gaps=["gRPC"],
            gap_analogues=[GapAnaloguesInput(gap="gRPC", analogues=[analogue])],
        )

    assert error.value.message == f"Факти не знайдено: #{theirs}."
    with pytest.raises(NotFound):
        world.get(world.alice, number)


def test_a_gap_analogue_for_a_gap_that_is_not_in_gaps_is_refused(
    world: World,
) -> None:
    number = world.seed(world.alice)
    rest = world.fact(world.alice, "skill", "REST", confirmed=True)
    analogue = AnalogueInput(fact_numbers=[rest], explanation="REST services")

    with pytest.raises(InvalidValue) as error:
        world.save(
            world.alice,
            number,
            gaps=["gRPC"],
            gap_analogues=[GapAnaloguesInput(gap="Rust", analogues=[analogue])],
        )

    assert error.value.message == "gap_analogues: «Rust» — такої прогалини нема в gaps."
