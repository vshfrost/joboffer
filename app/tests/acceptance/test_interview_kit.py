"""Кроки для features/interview_kit.feature: бриф і версії пакета до інтерв'ю, перевірка фактів
історій і тем питань. Use cases пакета + in-memory адаптери через портал.

Світ і допоміжні кроки (користувач, вакансія, тема) — з `test_prep_topics`. Вакансія, тема й факт —
за номером на користувача; внутрішній UUID у сценаріях не фігурує. Довгі значення для перевірки меж
пишуться як `а×500` (символ, «×», кількість), перенос рядка — як `\\n`.

Пакет у кроках збирається з чернетки: без уточнень це 5 питань, 3 історії на факті 1 і 3 питання до
компанії; рядки «пакет має …» замінюють окремі елементи, «у пакеті N питань, …» змінює кількість.
Чернетка стартує з типового пакета для кожного збереження.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.facts import FactData
from application.contracts.kit import (
    KitBriefData,
    KitData,
    KitInput,
    KitQuestionInput,
    StoryInput,
)
from application.ports.prompts import PromptKey
from application.prep.kit import InterviewKitUseCases
from domain.facts.fact import NewFact
from domain.facts.ids import FactId
from domain.shared.local_time import local_day
from tests.acceptance.test_prep_topics import World as TopicsWorld
from tests.acceptance.test_prep_topics import action, item, rx, text, words
from tests.support.clock import FakeClock
from tests.support.facts import InMemoryFactUnitOfWork
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.kit import InMemoryKitUnitOfWork, KitStore

scenarios("features/interview_kit.feature")

Step = Callable[..., Any]

KIT_RULES = "Prepare the kit. Then call save_interview_kit."


class KitPrompts:
    def get(self, key: PromptKey) -> str:
        return {
            PromptKey.PREP_TOPIC_RULES: "Propose topics.",
            PromptKey.PREP_KIT_RULES: KIT_RULES,
        }[key]


def setup(pattern: str) -> Callable[[Step], Step]:
    """Передумова, що читається і після «Припустимо», і після «Якщо» (через «І»)."""

    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(step)
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


def generated_question(position: int) -> KitQuestionInput:
    kind = "technical" if position % 2 else "behavioral"
    return KitQuestionInput(kind=kind, question=f"Question {position}?")


def generated_story(position: int) -> StoryInput:
    return StoryInput(
        title=f"Story {position}",
        situation=f"Situation {position}",
        task=f"Task {position}",
        action=f"Action {position}",
        result=f"Result {position}",
        fact_ids=[1],
    )


def generated_company_question(position: int) -> str:
    return f"Company question {position}?"


@dataclass
class Draft:
    """Пакет, який Claude збирається зберегти."""

    questions: list[KitQuestionInput] = field(
        default_factory=lambda: [generated_question(n) for n in range(1, 6)]
    )
    stories: list[StoryInput] = field(
        default_factory=lambda: [generated_story(n) for n in range(1, 4)]
    )
    company_questions: list[str] = field(
        default_factory=lambda: [generated_company_question(n) for n in range(1, 4)]
    )

    def input(self) -> KitInput:
        return KitInput(
            questions=self.questions,
            stories=self.stories,
            company_questions=self.company_questions,
        )


def resize[T](items: list[T], count: int, make: Callable[[int], T]) -> None:
    del items[count:]
    items.extend(make(position) for position in range(len(items) + 1, count + 1))


def put[T](items: list[T], position: int, value: T, make: Callable[[int], T]) -> None:
    """Елемент `position` (з 1); недостаючі до нього добудовуються типовими."""
    resize(items, max(len(items), position), make)
    items[position - 1] = value


class World(TopicsWorld):
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        super().__init__(portal, clock, ids)
        self.facts_store = FactStore.empty()
        self.kit_store = KitStore.empty()
        self.kits = InterviewKitUseCases(
            lambda: InMemoryKitUnitOfWork(
                self.jobs_store, self.prep_store, self.facts_store, self.kit_store
            ),
            clock,
            ids,
            KitPrompts(),
        )
        self.draft = Draft()
        self.kit_brief: KitBriefData | None = None
        self.kit: KitData | None = None

    def reset_outcome(self) -> None:
        super().reset_outcome()
        self.kit_brief = None
        self.kit = None

    def add_fact(self, kind: str, fact_text: str, *, confirmed: bool) -> None:
        async def add() -> None:
            async with InMemoryFactUnitOfWork(self.facts_store) as uow:
                added = await uow.facts.add(
                    self.actor.user_id,
                    FactId(self.ids.new()),
                    NewFact.parse(kind=kind, text=fact_text),
                    self.clock.now(),
                )
                if confirmed:
                    await uow.facts.confirm(
                        self.actor.user_id, [added.number], self.clock.now()
                    )
                await uow.commit()

        self.portal.call(add)

    def save_kit(self, job: int) -> None:
        data = self.draft.input()
        self.draft = Draft()
        self.kit = self.attempt(
            lambda: self.kits.save_interview_kit(self.actor, job, data)
        )

    def latest(self, job: int) -> KitData | None:
        found: KitData | None = self.portal.call(
            self.kits.latest_interview_kit, self.actor, job
        )
        return found

    def shown_kit(self) -> KitData:
        assert self.error is None, self.error
        assert self.kit is not None, "пакет не збережено і не прочитано"
        return self.kit

    def shown_kit_brief(self) -> KitBriefData:
        assert self.error is None, self.error
        assert self.kit_brief is not None, "бриф не готували"
        return self.kit_brief


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def nth[T](items: tuple[T, ...], position: str, what: str) -> T:
    """Елемент `position` (з 1) або зрозуміла помилка, що його нема."""
    assert 1 <= int(position) <= len(items), f"{what} {position} у пакеті нема"
    return items[int(position) - 1]


def numbers(value: str) -> list[int]:
    return [int(part) for part in words(value)]


# --- хто я, передумови -------------------------------------------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_given(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@setup(
    r'^є проаналізована вакансія "(?P<title>[^"]*)"(?: компанії "(?P<company>[^"]*)")?'
    r' зі скором (?P<score>\d+)(?: і прогалинами "(?P<gaps>[^"]*)")?$'
)
def analysed_job(
    world: World, title: str, company: str | None, score: str, gaps: str | None
) -> None:
    world.add_job(title, company or "")
    number = len(
        [key for key in world.jobs_store.jobs if key[0] == world.actor.user_id]
    )
    world.analyse(number, int(score), words(gaps or ""))


@setup(r'^є вакансія без аналізу "(?P<title>[^"]*)"$')
def unanalysed_job(world: World, title: str) -> None:
    world.add_job(title, "")


@action(
    r'^я (?:зберіг|зберігаю) тему "(?P<slug>[^"]*)" для вакансії (?P<job>\d+) з gap "(?P<gap>[^"]*)"$'
)
def save_topic(world: World, slug: str, job: str, gap: str) -> None:
    world.save(int(job), [item(slug, gap)])


@setup(
    r'^у мене є (?P<state>підтверджений|непідтверджений) факт (?P<kind>\w+) "(?P<fact>[^"]*)"$'
)
def fact(world: World, state: str, kind: str, fact: str) -> None:
    world.add_fact(kind, fact, confirmed=state == "підтверджений")


@bdd_given(rx(r'^годинник показує "(?P<moment>[^"]*)" за UTC$'))
@bdd_when(rx(r'^годинник показує "(?P<moment>[^"]*)" за UTC$'))
def clock_shows(world: World, moment: str) -> None:
    target = datetime.strptime(moment, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    world.clock.advance(target - world.clock.now())


# --- чернетка пакета ---------------------------------------------------------------------------


@setup(
    r"^у пакеті (?P<questions>\d+) питань, (?P<stories>\d+) історій"
    r" і (?P<company>\d+) питань до компанії$"
)
def sized(world: World, questions: str, stories: str, company: str) -> None:
    draft = world.draft
    resize(draft.questions, int(questions), generated_question)
    resize(draft.stories, int(stories), generated_story)
    resize(draft.company_questions, int(company), generated_company_question)


@setup(
    r'^пакет має питання (?P<position>\d+) "(?P<question>[^"]*)" виду "(?P<kind>[^"]*)"'
    r"(?: з темою (?P<topic>\d+))?$"
)
def draft_question(
    world: World, position: str, question: str, kind: str, topic: str | None
) -> None:
    value = KitQuestionInput(
        kind=kind,
        question=text(question),
        topic_number=None if topic is None else int(topic),
    )
    put(world.draft.questions, int(position), value, generated_question)


@setup(
    r'^пакет має історію (?P<position>\d+) "(?P<title>[^"]*)" з частинами "(?P<parts>[^"]*)"'
    r' на фактах "(?P<facts>[^"]*)"$'
)
def draft_story(
    world: World, position: str, title: str, parts: str, facts: str
) -> None:
    situation, task, action_part, result = (text(part) for part in words(parts))
    value = StoryInput(
        title=text(title),
        situation=situation,
        task=task,
        action=action_part,
        result=result,
        fact_ids=numbers(facts),
    )
    put(world.draft.stories, int(position), value, generated_story)


@setup(r'^пакет має питання до компанії (?P<position>\d+) "(?P<question>[^"]*)"$')
def draft_company_question(world: World, position: str, question: str) -> None:
    put(
        world.draft.company_questions,
        int(position),
        text(question),
        generated_company_question,
    )


# --- бриф --------------------------------------------------------------------------------------


@bdd_when(rx(r"^я готую пакет до вакансії (?P<job>\d+)$"))
def prepare_kit(world: World, job: str) -> None:
    world.kit_brief = world.attempt(
        lambda: world.kits.prepare_interview_kit(world.actor, int(job))
    )


@bdd_then(rx(r'^у брифі вакансія "(?P<title>[^"]*)"$'))
def brief_job(world: World, title: str) -> None:
    assert world.shown_kit_brief().job.title == title


@bdd_then(rx(r"^у брифі аналіз зі скором (?P<score>\d+)$"))
def brief_analysis(world: World, score: str) -> None:
    analysis = world.shown_kit_brief().analysis
    assert analysis is not None, "аналізу в брифі нема"
    assert analysis.score == int(score)


@bdd_then(rx(r"^у брифі аналізу нема$"))
def brief_no_analysis(world: World) -> None:
    assert world.shown_kit_brief().analysis is None


@bdd_then(rx(r'^у брифі теми за порядком: "(?P<slugs>[^"]*)"$'))
def brief_topics(world: World, slugs: str) -> None:
    assert [topic.slug for topic in world.shown_kit_brief().topics] == words(slugs)


@bdd_then(rx(r"^у брифі тем нема$"))
def brief_no_topics(world: World) -> None:
    assert world.shown_kit_brief().topics == ()


@bdd_then(rx(r'^у брифі підтверджені факти: "(?P<facts>[^"]*)"$'))
def brief_facts(world: World, facts: str) -> None:
    shown: tuple[FactData, ...] = world.shown_kit_brief().confirmed_facts
    assert all(fact.confirmed for fact in shown)
    assert sorted(fact.fact_number for fact in shown) == numbers(facts)


@bdd_then(rx(r"^у брифі підтверджених фактів нема$"))
def brief_no_facts(world: World) -> None:
    assert world.shown_kit_brief().confirmed_facts == ()


@bdd_then(rx(r'^правила пакета у брифі: "(?P<rules>[^"]*)"$'))
def brief_rules(world: World, rules: str) -> None:
    assert world.shown_kit_brief().rules == rules


@bdd_then(rx(r"^у брифі попередньої версії нема$"))
def brief_no_previous(world: World) -> None:
    assert world.shown_kit_brief().previous is None


@bdd_then(
    rx(
        r'^у брифі попередня версія (?P<version>\d+) з першим питанням "(?P<question>[^"]*)"$'
    )
)
def brief_previous(world: World, version: str, question: str) -> None:
    previous = world.shown_kit_brief().previous
    assert previous is not None, "попередньої версії в брифі нема"
    assert previous.version == int(version)
    assert nth(previous.questions, "1", "питання").question == question


# --- збереження й читання ----------------------------------------------------------------------


@action(r"^я (?:зберігаю|зберіг) пакет до вакансії (?P<job>\d+)$")
def save_kit(world: World, job: str) -> None:
    world.save_kit(int(job))


@bdd_when(rx(r"^я читаю останній пакет вакансії (?P<job>\d+)$"))
def read_kit(world: World, job: str) -> None:
    world.kit = world.attempt(
        lambda: world.kits.latest_interview_kit(world.actor, int(job))
    )


@bdd_then(
    rx(
        r"^збережено версію (?P<version>\d+) пакета вакансії (?P<job>\d+)"
        r" під номером (?P<number>\d+)$"
    )
)
def saved_version(world: World, version: str, job: str, number: str) -> None:
    kit = world.shown_kit()
    assert (kit.version, kit.job_number, kit.kit_number) == (
        int(version),
        int(job),
        int(number),
    )


@bdd_then(rx(r'^версію створено "(?P<day>\d{4}-\d{2}-\d{2})"$'))
def created_day(world: World, day: str) -> None:
    assert local_day(world.shown_kit().created_at) == day


@bdd_then(
    rx(
        r"^у пакеті питань (?P<questions>\d+), історій (?P<stories>\d+),"
        r" питань до компанії (?P<company>\d+)$"
    )
)
def kit_sizes(world: World, questions: str, stories: str, company: str) -> None:
    kit = world.shown_kit()
    assert (len(kit.questions), len(kit.stories), len(kit.company_questions)) == (
        int(questions),
        int(stories),
        int(company),
    )


@bdd_then(
    rx(
        r'^питання (?P<position>\d+) пакета: (?P<kind>technical|behavioral) "(?P<question>[^"]*)"$'
    )
)
def kit_question(world: World, position: str, kind: str, question: str) -> None:
    found = nth(world.shown_kit().questions, position, "питання")
    assert (found.kind, found.question) == (kind, text(question))


@bdd_then(rx(r"^тема питання (?P<position>\d+) пакета — (?P<topic>\d+|нема)$"))
def kit_question_topic(world: World, position: str, topic: str) -> None:
    found = nth(world.shown_kit().questions, position, "питання")
    assert found.topic_number == (None if topic == "нема" else int(topic))


@bdd_then(
    rx(
        r'^історія (?P<position>\d+) пакета "(?P<title>[^"]*)" має частини "(?P<parts>[^"]*)"$'
    )
)
def kit_story_parts(world: World, position: str, title: str, parts: str) -> None:
    story = nth(world.shown_kit().stories, position, "історії")
    assert story.title == text(title)
    assert [story.situation, story.task, story.action, story.result] == [
        text(part) for part in words(parts)
    ]


@bdd_then(
    rx(
        r'^історія (?P<position>\d+) пакета "(?P<title>[^"]*)" стоїть на фактах "(?P<facts>[^"]*)"$'
    )
)
def kit_story_facts(world: World, position: str, title: str, facts: str) -> None:
    story = nth(world.shown_kit().stories, position, "історії")
    assert story.title == text(title)
    assert list(story.fact_ids) == numbers(facts)


@bdd_then(rx(r'^питання до компанії (?P<position>\d+) пакета: "(?P<question>[^"]*)"$'))
def kit_company_question(world: World, position: str, question: str) -> None:
    found = nth(world.shown_kit().company_questions, position, "питання до компанії")
    assert found == text(question)


@bdd_then(rx(r"^остання версія пакета вакансії (?P<job>\d+) — (?P<version>\d+)$"))
def latest_version(world: World, job: str, version: str) -> None:
    latest = world.latest(int(job))
    assert latest is not None, "пакета нема"
    assert latest.version == int(version)


@bdd_then(rx(r"^пакета вакансії (?P<job>\d+) нема$"))
def no_kit(world: World, job: str) -> None:
    assert world.latest(int(job)) is None


# --- результат ---------------------------------------------------------------------------------


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def error_message(world: World, code: str, message: str) -> None:
    assert world.error is not None, "помилки не було"
    assert (world.error.code, world.error.message) == (code, text(message))
