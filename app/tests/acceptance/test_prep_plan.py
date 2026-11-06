"""Кроки для features/prep_plan.feature: план теми підготовки, виконання кроків, статус «готово».

Світ і допоміжні кроки (користувач, вакансія, тема) — з `test_prep_topics`; тут — use cases плану
+ in-memory адаптери через портал. Крок і тема — за номером на користувача; внутрішній UUID у
сценаріях не фігурує. План у кроках: `"learn, practice, check"` (або `"practice, check, 10 learn"`),
назви «Крок N» і 30 хвилин; `де крок N: вид "…", назва "…", хвилин "…", деталі "…", ресурси "…"`
замінює поля N-го кроку. Ресурси: `"Назва | url; Назва | url"` або `"10 шт"`.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.prep import (
    PlanBriefData,
    ResourceInput,
    StepData,
    StepInput,
    TopicData,
    TopicDetailData,
)
from application.ports.prompts import PromptKey
from application.prep.use_cases import PrepUseCases
from domain.shared.errors import DomainError
from domain.shared.local_time import local_day
from tests.acceptance.test_prep_topics import World as TopicsWorld
from tests.acceptance.test_prep_topics import action, item, rx, text, words
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.prep import InMemoryPrepUnitOfWork

scenarios("features/prep_plan.feature")

RULES = "Write a plan. Then call save_topic_plan."
FIELD = re.compile(r'([^\s"]+) "([^"]*)"')
COUNTED = re.compile(r"(\d+) (\w+)")
COUNTED_RESOURCES = re.compile(r"(\d+) шт")


class PlanPrompts:
    def get(self, key: PromptKey) -> str:
        return {PromptKey.PREP_PLAN_RULES: RULES}[key]


class World(TopicsWorld):
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        super().__init__(portal, clock, ids)
        self.prep = PrepUseCases(
            lambda: InMemoryPrepUnitOfWork(self.jobs_store, self.prep_store),
            clock,
            ids,
            PlanPrompts(),
        )
        self.plan_brief: PlanBriefData | None = None
        self.shown: TopicDetailData | None = None
        self.returned: TopicDetailData | None = None

    def reset_outcome(self) -> None:
        super().reset_outcome()
        self.plan_brief = None
        self.shown = None
        self.returned = None

    def read(self, topic: int) -> TopicDetailData:
        try:
            detail: TopicDetailData = self.portal.call(
                self.prep.get_topic, self.actor, topic
            )
        except DomainError as error:
            raise AssertionError(f"тему {topic} не прочитано: {error}") from error
        return detail

    def step(self, number: int) -> StepData | None:
        """Крок за номером користувача: шукає по всіх його темах."""
        for topic in self.topics():
            for found in self.read(topic.topic_number).steps:
                if found.step_number == number:
                    return found
        return None

    def shown_detail(self) -> TopicDetailData:
        assert self.error is None, self.error
        assert self.shown is not None, "тему не показували"
        return self.shown


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def plan_steps(
    kinds: str, index: int | None = None, fields: dict[str, str] | None = None
) -> list[StepInput]:
    names: list[str] = []
    for part in words(kinds.replace(",", ";")):
        counted = COUNTED.fullmatch(part)
        if counted:
            names += [counted[2]] * int(counted[1])
        else:
            names.append(part)
    steps = [
        StepInput(kind=name, title=f"Крок {n}", minutes=30)
        for n, name in enumerate(names, 1)
    ]
    if index is not None and fields is not None:
        steps[index - 1] = changed(steps[index - 1], fields)
    return steps


def resources(value: str) -> list[ResourceInput]:
    counted = COUNTED_RESOURCES.fullmatch(value)
    if counted:
        return [
            ResourceInput(title=f"Ресурс {n}", url=f"https://example.com/{n}")
            for n in range(1, int(counted[1]) + 1)
        ]
    found = []
    for part in value.split(";"):
        title, _, url = part.partition("|")
        found.append(ResourceInput(title=title.strip(), url=url.strip()))
    return found


def changed(step: StepInput, fields: dict[str, str]) -> StepInput:
    values: dict[str, Any] = {
        "kind": step.kind,
        "title": step.title,
        "minutes": step.minutes,
        "details": step.details,
        "resources": list(step.resources),
    }
    for name, raw in fields.items():
        value = text(raw)
        match name:
            case "вид":
                values["kind"] = value
            case "назва":
                values["title"] = value
            case "хвилин":
                values["minutes"] = int(value)
            case "деталі":
                values["details"] = value
            case "ресурси":
                values["resources"] = resources(value)
            case _:
                raise AssertionError(f"невідоме поле кроку: {name}")
    return StepInput(**values)


def line(step: StepData) -> str:
    done = " (виконано)" if step.done_at is not None else ""
    return f"{step.step_number} {step.kind.value} {step.title}{done}"


# --- хто я, передумови (як у test_prep_topics) -------------------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_given(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@bdd_given(
    rx(
        r'^є проаналізована вакансія "(?P<title>[^"]*)"(?: компанії "(?P<company>[^"]*)")?'
        r' зі скором (?P<score>\d+)(?: і прогалинами "(?P<gaps>[^"]*)")?$'
    )
)
def analysed_job(
    world: World, title: str, company: str | None, score: str, gaps: str | None
) -> None:
    world.add_job(title, company or "")
    number = len(
        [key for key in world.jobs_store.jobs if key[0] == world.actor.user_id]
    )
    world.analyse(number, int(score), words(gaps or ""))


@action(
    r'^я (?:зберігаю|зберіг) тему "(?P<slug>[^"]*)" для вакансії (?P<job>\d+) з gap "(?P<gap>[^"]*)"$'
)
def save_topic(world: World, slug: str, job: str, gap: str) -> None:
    world.save(int(job), [item(slug, gap)])


@bdd_given(rx(r"^минуло (?P<days>\d+) (?:день|дні|днів)$"))
def days_passed(world: World, days: str) -> None:
    world.clock.advance(timedelta(days=int(days)))


@bdd_given(rx(r'^годинник показує "(?P<moment>[^"]*)" за UTC$'))
def clock_shows(world: World, moment: str) -> None:
    target = datetime.strptime(moment, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    world.clock.advance(target - world.clock.now())


# --- бриф --------------------------------------------------------------------------------------


@bdd_when(rx(r"^я готую план теми (?P<topic>\d+)$"))
def prepare_plan(world: World, topic: str) -> None:
    world.plan_brief = world.attempt(
        lambda: world.prep.prepare_topic_plan(world.actor, int(topic))
    )
    if world.plan_brief is not None:
        world.shown = world.plan_brief.detail


@bdd_then(rx(r'^в брифі тема "(?P<slug>[^"]*)" зі статусом "(?P<status>[^"]*)"$'))
def brief_topic(world: World, slug: str, status: str) -> None:
    assert world.error is None, world.error
    assert world.plan_brief is not None, "бриф не готували"
    topic = world.plan_brief.detail.topic
    assert (topic.slug, topic.status.value) == (slug, status)


@bdd_then(rx(r"^у брифі кроків (?P<count>\d+)$"))
def brief_steps(world: World, count: str) -> None:
    assert world.error is None, world.error
    assert world.plan_brief is not None, "бриф не готували"
    assert len(world.plan_brief.detail.steps) == int(count)


@bdd_then(rx(r'^правила плану в брифі: "(?P<rules>[^"]*)"$'))
def brief_rules(world: World, rules: str) -> None:
    assert world.error is None, world.error
    assert world.plan_brief is not None, "бриф не готували"
    assert world.plan_brief.rules == rules


@bdd_then(rx(r'^тема прив\'язана до вакансій: "(?P<jobs>[^"]*)"$'))
def shown_jobs(world: World, jobs: str) -> None:
    linked = [
        f"{job.job_number}: {job.gap} (скор {job.score})"
        for job in world.shown_detail().topic.jobs
    ]
    assert linked == words(jobs)


# --- збереження плану --------------------------------------------------------------------------


def save_plan(world: World, topic: int, items: list[StepInput]) -> None:
    detail = world.attempt(
        lambda: world.prep.save_topic_plan(world.actor, topic, items)
    )
    world.returned = detail
    world.shown = detail


@action(
    r'^я (?:зберігаю|зберіг) план теми (?P<topic>\d+) з кроками "(?P<kinds>[^"]*)"'
    r'(?:, де крок (?P<index>\d+): (?P<fields>(?:[^\s"]+ "[^"]*"(?:, )?)+))?$'
)
def save_plan_by_kinds(
    world: World, topic: str, kinds: str, index: str | None, fields: str | None
) -> None:
    changes = dict(FIELD.findall(fields)) if fields else None
    save_plan(
        world,
        int(topic),
        plan_steps(kinds, int(index) if index else None, changes),
    )


@action(r"^я (?:зберігаю|зберіг) план теми (?P<topic>\d+):$")
def save_plan_table(world: World, datatable: list[list[str]], topic: str) -> None:
    items = [
        StepInput(kind=kind, title=title, minutes=int(minutes))
        for kind, title, minutes in datatable[1:]
    ]
    save_plan(world, int(topic), items)


@bdd_then(rx(r'^кроки теми (?P<topic>\d+) за порядком: "(?P<steps>[^"]*)"$'))
def steps_in_order(world: World, topic: str, steps: str) -> None:
    assert [line(s) for s in world.read(int(topic)).steps] == words(steps)


@bdd_then(rx(r"^у плані теми (?P<topic>\d+) кроків (?P<count>\d+)$"))
def steps_count(world: World, topic: str, count: str) -> None:
    assert len(world.read(int(topic)).steps) == int(count)


@bdd_then(
    rx(
        r'^крок (?P<step>\d+) теми (?P<topic>\d+): деталі "(?P<details>[^"]*)", ресурси "(?P<links>[^"]*)"$'
    )
)
def step_content(world: World, step: str, topic: str, details: str, links: str) -> None:
    found = world.read(int(topic)).steps[int(step) - 1]
    shown = [f"{r.title} | {r.url}" for r in found.resources]
    assert (found.details, shown) == (details, words(links))


@bdd_then(rx(r"^збережена тема збігається з прочитаною$"))
@bdd_then(rx(r"^повернена тема збігається з прочитаною$"))
def returned_equals_read(world: World) -> None:
    assert world.error is None, world.error
    assert world.returned is not None, "дія нічого не повернула"
    assert world.returned == world.read(world.returned.topic.topic_number)


# --- виконання кроку, «готово» ----------------------------------------------------------------


@action(
    r'^я (?:завершую|завершив) крок (?P<step>\d+)(?: з нотаткою "(?P<note>[^"]*)")?$'
)
def complete_step(world: World, step: str, note: str | None) -> None:
    world.returned = world.attempt(
        lambda: world.prep.complete_step(world.actor, int(step), text(note or ""))
    )
    world.shown = world.returned


@action(r"^я (?:позначаю|позначив) тему (?P<topic>\d+) готовою$")
def mark_ready(world: World, topic: str) -> None:
    world.returned = world.attempt(
        lambda: world.prep.set_topic_ready(world.actor, int(topic))
    )
    world.shown = world.returned


@action(r"^я (?:знімаю|зняв) позначку «готово» з теми (?P<topic>\d+)$")
def unmark_ready(world: World, topic: str) -> None:
    world.returned = world.attempt(
        lambda: world.prep.set_topic_ready(world.actor, int(topic), ready=False)
    )
    world.shown = world.returned


@bdd_then(
    rx(
        r'^крок (?P<step>\d+) виконано (?P<day>\d{4}-\d{2}-\d{2}) з нотаткою "(?P<note>[^"]*)"$'
    )
)
def step_done(world: World, step: str, day: str, note: str) -> None:
    assert world.error is None, world.error
    found = world.step(int(step))
    assert found is not None, f"кроку {step} нема"
    assert found.done_at is not None, f"крок {step} не виконано"
    assert (local_day(found.done_at), found.note) == (day, text(note))


@bdd_then(rx(r"^крок (?P<step>\d+) не виконано$"))
def step_pending(world: World, step: str) -> None:
    found = world.step(int(step))
    assert found is not None, f"кроку {step} нема"
    assert found.done_at is None


# --- перегляд теми -----------------------------------------------------------------------------


@bdd_when(rx(r"^я дивлюся тему (?P<topic>\d+)$"))
def view_topic(world: World, topic: str) -> None:
    world.shown = world.attempt(lambda: world.prep.get_topic(world.actor, int(topic)))


@bdd_when(rx(r"^я переглядаю теми$"))
def view_topics(world: World) -> None:
    world.listed = world.attempt(lambda: world.prep.list_prep_topics(world.actor))


def summary(topic: TopicData) -> str:
    return (
        f'статус "{topic.status.value}", виконано {topic.steps_done} з '
        f"{topic.steps_total}, лишилось {topic.minutes_left} хв"
    )


@bdd_then(
    rx(
        r'^тема (?P<topic>\d+): статус "(?P<status>[^"]*)", виконано (?P<done>\d+) з (?P<total>\d+), '
        r"лишилось (?P<minutes>\d+) хв$"
    )
)
def topic_progress(
    world: World, topic: str, status: str, done: str, total: str, minutes: str
) -> None:
    shown = world.read(int(topic)).topic
    expected = (status, int(done), int(total), int(minutes))
    assert (
        shown.status.value,
        shown.steps_done,
        shown.steps_total,
        shown.minutes_left,
    ) == expected


@bdd_then(
    rx(
        r'^у списку тема "(?P<slug>[^"]*)": статус "(?P<status>[^"]*)", виконано (?P<done>\d+) з (?P<total>\d+), '
        r"лишилось (?P<minutes>\d+) хв$"
    )
)
def listed_progress(
    world: World, slug: str, status: str, done: str, total: str, minutes: str
) -> None:
    assert world.error is None, world.error
    assert world.listed is not None, "теми не переглядали"
    shown = next(topic for topic in world.listed if topic.slug == slug)
    assert summary(shown) == (
        f'статус "{status}", виконано {done} з {total}, лишилось {minutes} хв'
    )


@bdd_then(rx(r"^наступний крок теми (?P<topic>\d+) — (?P<step>\d+)$"))
def next_step(world: World, topic: str, step: str) -> None:
    assert world.read(int(topic)).next_step_number == int(step)


@bdd_then(rx(r"^наступного кроку теми (?P<topic>\d+) нема$"))
def no_next_step(world: World, topic: str) -> None:
    assert world.read(int(topic)).next_step_number is None


# --- результат ---------------------------------------------------------------------------------


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def error_message(world: World, code: str, message: str) -> None:
    assert world.error is not None, "помилки не було"
    assert (world.error.code, world.error.message) == (code, text(message))
