"""Бриф тем підготовки містить рядки CV вакансії з їхніми фактами: те, що вже написано в CV, теж
треба вміти захистити на інтерв'ю (ATS-5)."""

from datetime import UTC, datetime

import pytest
from anyio.from_thread import BlockingPortal

from application.analysis.use_cases import AnalysisUseCases
from application.contracts.actor import Actor, Channel, Scope
from application.contracts.analysis import AnalysisInput
from application.contracts.jobs import JobInput
from application.contracts.prep import TopicsBriefData
from application.jobs.use_cases import JobUseCases
from application.ports.prompts import PromptKey
from application.prep.use_cases import PrepUseCases
from domain.documents.document import Claim, Cv, CvEntry, CvSection, CvSectionName
from domain.documents.ids import DocumentId
from domain.facts.fact import FactKind, NewFact
from domain.facts.ids import FactId
from domain.identity.ids import UserId
from tests.support.analysis import InMemoryAnalysisUnitOfWork
from tests.support.clock import FakeClock
from tests.support.documents import DocumentStore, InMemoryDocuments
from tests.support.facts import InMemoryFacts
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store
from tests.support.prep import InMemoryPrepUnitOfWork, PrepStore

RULES = "Propose topics for the gaps."
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


class FakePrompts:
    def get(self, key: PromptKey) -> str:
        return {PromptKey.PREP_TOPIC_RULES: RULES}[key]


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.ids = ids
        self.jobs_store = Store.empty()
        self.facts_store = FactStore.empty()
        self.docs_store = DocumentStore.empty()
        self.actor = Actor(
            user_id=UserId(ids.new()),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )
        self.jobs = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.jobs_store), clock, ids
        )
        self.analysis = AnalysisUseCases(
            lambda: InMemoryAnalysisUnitOfWork(
                self.jobs_store, FactStore.empty(), {}, {}
            ),
            clock,
            ids,
            FakePrompts(),
        )
        self.prep = PrepUseCases(
            lambda: InMemoryPrepUnitOfWork(
                self.jobs_store, PrepStore.empty(), self.facts_store, self.docs_store
            ),
            clock,
            ids,
            FakePrompts(),
        )

    def analysed_job(self, title: str, gaps: list[str]) -> int:
        data = JobInput(text=f"Опис {title}", title=title, company="Acme")
        self.portal.call(self.jobs.add_job, self.actor, data)
        number = len(self.jobs_store.jobs)
        analysis = AnalysisInput(score=80, summary="Підсумок.", gaps=gaps)
        self.portal.call(self.analysis.save_analysis, self.actor, number, analysis)
        return number

    def fact(self, text: str) -> int:
        new = NewFact(FactKind.EXPERIENCE, text, confirmed=True)

        async def add() -> int:
            added = await InMemoryFacts(self.facts_store).add(
                self.actor.user_id, FactId(self.ids.new()), new, NOW
            )
            return added.number

        return self.portal.call(add)

    def cv(self, job: int, *lines: tuple[str, int]) -> None:
        """Нова версія CV вакансії: перший рядок — заголовок, другий — підсумок, третій —
        заголовок пункту Experience, решта — його пункти."""
        (headline, summary, *rest) = (Claim(text, (fact,)) for text, fact in lines)
        entry = CvEntry(heading=rest[0], bullets=tuple(rest[1:]))
        content = Cv(
            headline=headline,
            summary=summary,
            sections=(CvSection(CvSectionName.EXPERIENCE, (entry,)),),
        )
        job_id = self.jobs_store.jobs[(self.actor.user_id, job)].id

        async def add() -> None:
            documents = InMemoryDocuments(self.jobs_store, self.docs_store)
            await documents.add(
                self.actor.user_id, DocumentId(self.ids.new()), job_id, content, NOW
            )

        self.portal.call(add)

    def brief(self, job: int) -> TopicsBriefData:
        return self.portal.call(self.prep.prepare_prep_topics, self.actor, job)


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def lines(brief: TopicsBriefData) -> list[tuple[str, list[str]]]:
    return [(line.text, [fact.text for fact in line.facts]) for line in brief.cv_lines]


def test_a_job_with_a_cv_brings_the_cv_lines_with_their_facts(world: World) -> None:
    job = world.analysed_job("Fullstack", ["Kafka"])
    years = world.fact("4+ years of full-stack development")
    state = world.fact("Owned state management in a React app")
    world.cv(
        job,
        ("Full-stack engineer", years),
        ("4+ years full stack", years),
        ("Acme", years),
        ("Designed state management for 12 screens", state),
    )

    assert lines(world.brief(job)) == [
        ("Full-stack engineer", ["4+ years of full-stack development"]),
        ("4+ years full stack", ["4+ years of full-stack development"]),
        ("Acme", ["4+ years of full-stack development"]),
        (
            "Designed state management for 12 screens",
            ["Owned state management in a React app"],
        ),
    ]


def test_a_fact_carries_its_number(world: World) -> None:
    job = world.analysed_job("Fullstack", [])
    first = world.fact("Built payment APIs")
    second = world.fact("Led a team of 5")
    world.cv(job, ("Engineer", first), ("Payments", first), ("Acme", second))

    brief = world.brief(job)

    assert [fact.fact_number for line in brief.cv_lines for fact in line.facts] == [
        first,
        first,
        second,
    ]


def test_the_latest_cv_version_is_used(world: World) -> None:
    job = world.analysed_job("Fullstack", [])
    fact = world.fact("Built payment APIs")
    world.cv(job, ("Old title", fact), ("Old", fact), ("Acme", fact))
    world.cv(job, ("New title", fact), ("New", fact), ("Acme", fact))

    assert [text for text, _ in lines(world.brief(job))][:2] == ["New title", "New"]


def test_a_job_without_a_cv_has_no_cv_lines_and_the_rest_as_before(
    world: World,
) -> None:
    job = world.analysed_job("Fullstack", ["Kafka", "MySQL"])

    brief = world.brief(job)

    assert brief.cv_lines == ()
    assert brief.job.title == "Fullstack"
    assert [item.gap for item in brief.analysis.gaps] == ["Kafka", "MySQL"]
    assert brief.topics == ()
    assert brief.rules == RULES


def test_the_cv_of_another_job_is_not_used(world: World) -> None:
    with_cv = world.analysed_job("Fullstack", [])
    without_cv = world.analysed_job("Backend", [])
    fact = world.fact("Built payment APIs")
    world.cv(with_cv, ("Engineer", fact), ("Payments", fact), ("Acme", fact))

    assert world.brief(without_cv).cv_lines == ()


def test_the_gaps_stay_in_the_brief_next_to_the_cv_lines(world: World) -> None:
    job = world.analysed_job("Fullstack", ["Kafka"])
    fact = world.fact("Built payment APIs")
    world.cv(job, ("Engineer", fact), ("Payments", fact), ("Acme", fact))

    brief = world.brief(job)

    assert [item.gap for item in brief.analysis.gaps] == ["Kafka"]
    assert len(brief.cv_lines) == 3
